"""Local inference worker: Whisper STT and Kokoro TTS over HTTP.

Kept in its own container so the API process stays light and the models load
once. Both engines are loaded lazily on first use and cached, so the health
endpoint answers immediately at boot while a cold model is still downloading.

Everything here is free and offline. No request leaves the machine.
"""

from __future__ import annotations

import io
import logging
import os
import struct
import tempfile
import threading
import wave
from typing import Any

import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import Response
from pydantic import BaseModel, Field

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("worker")

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base.en")
KOKORO_VOICE = os.getenv("KOKORO_VOICE", "af_heart")
KOKORO_SAMPLE_RATE = 24_000

app = FastAPI(title="CallSentry Worker", version="1.0.0")

# Models are not thread-safe and are expensive to load; guard both.
_whisper: Any = None
_whisper_lock = threading.Lock()
_kokoro: Any = None
_kokoro_lock = threading.Lock()


def _load_whisper() -> Any:
    """faster-whisper is a CTranslate2 port of whisper.cpp - same models, no GPU needed."""
    global _whisper
    if _whisper is None:
        with _whisper_lock:
            if _whisper is None:
                from faster_whisper import WhisperModel

                log.info("loading whisper model=%s", WHISPER_MODEL)
                _whisper = WhisperModel(
                    WHISPER_MODEL,
                    device="cpu",
                    compute_type="int8",
                    download_root="/models",
                )
                log.info("whisper ready")
    return _whisper


def _load_kokoro() -> Any:
    global _kokoro
    if _kokoro is None:
        with _kokoro_lock:
            if _kokoro is None:
                from kokoro import KPipeline

                log.info("loading kokoro pipeline")
                _kokoro = KPipeline(lang_code="a")  # 'a' = American English
                log.info("kokoro ready")
    return _kokoro


def _to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """Float32 [-1,1] -> 16-bit PCM WAV."""
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _silence(seconds: float = 0.4, sample_rate: int = KOKORO_SAMPLE_RATE) -> bytes:
    n = int(seconds * sample_rate)
    data = b"\x00\x00" * n
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    return header + b"data" + struct.pack("<I", len(data)) + data


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    voice: str = KOKORO_VOICE
    speed: float = Field(default=1.0, ge=0.5, le=2.0)


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "whisper_model": WHISPER_MODEL,
        "whisper_loaded": _whisper is not None,
        "kokoro_loaded": _kokoro is not None,
    }


@app.post("/warmup")
async def warmup() -> dict[str, str]:
    """Force both models to load. Called once after `make up` to avoid a cold
    first call, which would otherwise blow the latency budget on a real caller."""
    _load_whisper()
    _load_kokoro()
    return {"status": "warm"}


@app.post("/stt")
async def transcribe(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty audio")

    with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp:
        tmp.write(data)
        tmp.flush()
        try:
            model = _load_whisper()
            segments, info = model.transcribe(
                tmp.name,
                beam_size=1,          # greedy: fastest, adequate for phone audio
                vad_filter=True,      # drop silence so hold music isn't "transcribed"
                language="en",
            )
            text = " ".join(segment.text.strip() for segment in segments).strip()
        except Exception as exc:
            log.exception("stt failed")
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, f"transcription failed: {exc}"
            ) from exc

    return {
        "text": text,
        "duration_seconds": round(float(getattr(info, "duration", 0.0)), 2),
        "language": getattr(info, "language", "en"),
        "provider": "whisper.cpp",
    }


@app.post("/tts")
async def synthesize(payload: TTSRequest) -> Response:
    try:
        pipeline = _load_kokoro()
        chunks = [
            audio for _gs, _ps, audio in pipeline(payload.text, voice=payload.voice,
                                                  speed=payload.speed)
        ]
        if not chunks:
            raise ValueError("kokoro produced no audio")
        samples = np.concatenate([np.asarray(c, dtype=np.float32) for c in chunks])
        wav = _to_wav(samples, KOKORO_SAMPLE_RATE)
    except Exception as exc:
        # Returning silence keeps a live call alive; the API layer records the
        # degradation on the call's provider log.
        log.exception("tts failed, returning silence")
        return Response(
            content=_silence(),
            media_type="audio/wav",
            headers={"X-Degraded": "true", "X-Error": type(exc).__name__},
        )

    return Response(
        content=wav,
        media_type="audio/wav",
        headers={"X-Sample-Rate": str(KOKORO_SAMPLE_RATE), "X-Voice": payload.voice},
    )
