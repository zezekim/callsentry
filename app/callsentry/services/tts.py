"""Text-to-speech: Kokoro (local) -> ElevenLabs (cloud) -> silence.

The mock tier returns a short silent WAV rather than raising. On a live call
that is heard as a brief pause; the alternative - an exception mid-turn -
drops the caller.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

import httpx
import structlog

from callsentry.config import get_settings
from callsentry.core.providers import Attempt, Component, ProviderSpec, get_registry

log = structlog.get_logger(__name__)

ELEVENLABS_PER_1K_CHARS = 0.30


def silent_wav(seconds: float = 0.4, sample_rate: int = 24_000) -> bytes:
    """Minimal 16-bit mono PCM WAV of silence."""
    n = int(seconds * sample_rate)
    data = b"\x00\x00" * n
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, sample_rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(data))
    return header + data


@dataclass
class SpeechResult:
    audio: bytes
    mime_type: str
    provider: str
    tier: str
    characters: int = 0
    cost_usd: float = 0.0
    attempts: list[Attempt] = field(default_factory=list)


class TTSService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.registry = get_registry()

    async def _via_kokoro(self, text: str, voice: str) -> SpeechResult:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.settings.worker_base_url}/tts",
                json={"text": text, "voice": voice},
            )
            resp.raise_for_status()
        return SpeechResult(
            audio=resp.content,
            mime_type="audio/wav",
            provider="kokoro",
            tier="local",
            characters=len(text),
            cost_usd=0.0,
        )

    async def _via_elevenlabs(self, text: str, voice: str) -> SpeechResult:
        # ElevenLabs voice ids are opaque; fall back to a stock voice when the
        # business is configured with a Kokoro voice name.
        voice_id = voice if len(voice) > 16 else "21m00Tcm4TlvDq8ikWAM"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
                headers={
                    "xi-api-key": self.settings.elevenlabs_api_key,
                    "Content-Type": "application/json",
                },
                json={"text": text, "model_id": "eleven_turbo_v2_5"},
            )
            resp.raise_for_status()
        return SpeechResult(
            audio=resp.content,
            mime_type="audio/mpeg",
            provider="elevenlabs",
            tier="cloud",
            characters=len(text),
            cost_usd=round(len(text) / 1000 * ELEVENLABS_PER_1K_CHARS, 6),
        )

    async def synthesize(self, text: str, *, voice: str = "af_heart") -> SpeechResult:
        attempts: list[Attempt] = []

        async def kokoro(_: ProviderSpec) -> SpeechResult:
            return await self._via_kokoro(text, voice)

        async def elevenlabs(_: ProviderSpec) -> SpeechResult:
            return await self._via_elevenlabs(text, voice)

        async def mock(_: ProviderSpec) -> SpeechResult:
            log.warning("tts.degraded_to_silence", chars=len(text))
            return SpeechResult(
                audio=silent_wav(),
                mime_type="audio/wav",
                provider="mock-tts",
                tier="mock",
                characters=len(text),
            )

        result, _ = await self.registry.run(
            Component.TTS,
            {"kokoro": kokoro, "elevenlabs": elevenlabs, "mock-tts": mock},
            attempts=attempts,
        )
        result.attempts = attempts
        return result


_service: TTSService | None = None


def get_tts() -> TTSService:
    global _service
    if _service is None:
        _service = TTSService()
    return _service
