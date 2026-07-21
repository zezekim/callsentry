"""The voice pipeline: endpointing, STT, turn dispatch, TTS, playback.

One `CallPipeline` instance per live call. It owns no conversation logic -
every caller utterance is posted to the API's /internal/turn endpoint, which
runs the state machine and returns what to say.

Endpointing (deciding when the caller has stopped talking) is energy-based:
we track RMS per 20 ms frame and treat a run of quiet frames after speech as
end-of-turn. That is cheap, has no model to load, and on a band-limited phone
line performs close to a neural VAD.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field

import httpx
import numpy as np

from agent import audio

log = logging.getLogger("agent.pipeline")

# Endpointing thresholds, in 20 ms frames.
SILENCE_FRAMES_TO_ENDPOINT = 35   # ~700 ms of quiet ends the turn
MIN_SPEECH_FRAMES = 10            # ~200 ms - below this it's a cough, not speech
MAX_UTTERANCE_FRAMES = 1500       # ~30 s hard cap so one rambling turn can't hang
SPEECH_RMS_THRESHOLD = 550.0      # int16 RMS; tuned for mu-law phone audio

# Barge-in: this much caller speech during playback cancels our audio.
BARGE_IN_FRAMES = 8


@dataclass
class CallContext:
    call_id: str
    stream_sid: str = ""
    greeting: str = ""
    voice: str = "af_heart"
    business_name: str = ""
    transcript: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.monotonic)

    def log_line(self, speaker: str, text: str) -> None:
        if text.strip():
            self.transcript.append(f"{speaker}: {text.strip()}")

    @property
    def full_transcript(self) -> str:
        return "\n".join(self.transcript)

    @property
    def duration_seconds(self) -> int:
        return int(time.monotonic() - self.started_at)


class Endpointer:
    """Accumulates caller frames and reports when a turn is complete."""

    def __init__(self) -> None:
        self.buffer: list[np.ndarray] = []
        self.speech_frames = 0
        self.silence_frames = 0
        self.triggered = False

    def reset(self) -> None:
        self.buffer.clear()
        self.speech_frames = 0
        self.silence_frames = 0
        self.triggered = False

    def push(self, samples: np.ndarray) -> bool:
        """Add one frame. Returns True when the utterance looks complete."""
        level = audio.rms(samples)
        is_speech = level > SPEECH_RMS_THRESHOLD

        if is_speech:
            self.triggered = True
            self.speech_frames += 1
            self.silence_frames = 0
        elif self.triggered:
            self.silence_frames += 1

        # Only buffer once speech has actually started, so we don't send
        # several seconds of line noise to the transcriber.
        if self.triggered:
            self.buffer.append(samples)

        if self.triggered and self.speech_frames >= MIN_SPEECH_FRAMES:
            if self.silence_frames >= SILENCE_FRAMES_TO_ENDPOINT:
                return True
        if len(self.buffer) >= MAX_UTTERANCE_FRAMES:
            return True
        return False

    def take(self) -> np.ndarray:
        samples = (
            np.concatenate(self.buffer) if self.buffer else np.zeros(0, dtype=np.int16)
        )
        self.reset()
        return samples


class CallPipeline:
    def __init__(
        self,
        *,
        context: CallContext,
        send_json,  # Callable[[dict], Awaitable[None]]
        app_base_url: str,
        worker_base_url: str,
        internal_token: str,
    ) -> None:
        self.ctx = context
        self.send_json = send_json
        self.app_base_url = app_base_url.rstrip("/")
        self.worker_base_url = worker_base_url.rstrip("/")
        self.internal_token = internal_token

        self.endpointer = Endpointer()
        self.speaking = False
        self.should_hangup = False
        self.transfer_to: str | None = None
        self._playback_task: asyncio.Task | None = None
        self._barge_frames = 0
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._cancel_playback()
        await self._client.aclose()

    # -- inbound ------------------------------------------------------------

    async def on_media(self, payload: str) -> None:
        """One 20 ms mu-law frame from the caller."""
        samples = audio.mulaw_decode(base64.b64decode(payload))

        if self.speaking:
            # Barge-in: if the caller talks over us, stop and listen.
            if audio.rms(samples) > SPEECH_RMS_THRESHOLD:
                self._barge_frames += 1
                if self._barge_frames >= BARGE_IN_FRAMES:
                    log.info("barge-in call_id=%s", self.ctx.call_id)
                    await self._cancel_playback()
                    await self._clear_twilio_buffer()
            else:
                self._barge_frames = 0
            return

        if self.endpointer.push(samples):
            utterance = self.endpointer.take()
            # Handle the turn off the receive loop so incoming frames keep
            # draining; otherwise Twilio's buffer overruns during inference.
            asyncio.create_task(self._handle_utterance(utterance))

    async def _handle_utterance(self, samples: np.ndarray) -> None:
        if samples.size == 0:
            return
        try:
            text = await self._transcribe(samples)
            if not text:
                return

            log.info("caller call_id=%s text=%r", self.ctx.call_id, text[:120])
            self.ctx.log_line("Caller", text)

            reply = await self._dispatch_turn(text)
            if reply is None:
                return

            self.ctx.log_line("Assistant", reply["text"])
            await self.say(reply["text"], voice=reply.get("voice", self.ctx.voice))

            if reply.get("transfer_to"):
                self.transfer_to = reply["transfer_to"]
                self.should_hangup = True
            elif reply.get("end_call"):
                self.should_hangup = True

        except Exception:
            log.exception("turn failed call_id=%s", self.ctx.call_id)
            # Never leave the caller in silence after an internal error.
            await self.say(
                "Sorry, I'm having a technical problem. Let me have someone call you back."
            )
            self.should_hangup = True

    async def _transcribe(self, samples: np.ndarray) -> str:
        wav = audio.pcm_to_wav(samples, audio.TWILIO_SAMPLE_RATE)
        try:
            resp = await self._client.post(
                f"{self.worker_base_url}/stt",
                files={"file": ("turn.wav", wav, "audio/wav")},
            )
            resp.raise_for_status()
            return str(resp.json().get("text", "")).strip()
        except httpx.HTTPError as exc:
            log.warning("stt unavailable call_id=%s error=%s", self.ctx.call_id, exc)
            return ""

    async def _dispatch_turn(self, utterance: str) -> dict | None:
        try:
            resp = await self._client.post(
                f"{self.app_base_url}/internal/turn",
                json={"call_id": self.ctx.call_id, "utterance": utterance},
                headers={"X-Internal-Token": self.internal_token},
            )
            resp.raise_for_status()
            return dict(resp.json())
        except httpx.HTTPError as exc:
            log.error("turn dispatch failed call_id=%s error=%s", self.ctx.call_id, exc)
            return None

    # -- outbound -----------------------------------------------------------

    async def say(self, text: str, *, voice: str | None = None) -> None:
        """Synthesise and stream audio to the caller."""
        if not text.strip():
            return
        await self._cancel_playback()

        try:
            resp = await self._client.post(
                f"{self.worker_base_url}/tts",
                json={"text": text, "voice": voice or self.ctx.voice},
            )
            resp.raise_for_status()
            frames = audio.wav_to_mulaw_frames(resp.content)
        except (httpx.HTTPError, ValueError) as exc:
            log.error("tts failed call_id=%s error=%s", self.ctx.call_id, exc)
            return

        self._playback_task = asyncio.create_task(self._stream(frames))
        await self._playback_task

    async def _stream(self, frames: list[bytes]) -> None:
        self.speaking = True
        self._barge_frames = 0
        self.endpointer.reset()
        try:
            for i, frame in enumerate(frames):
                await self.send_json(
                    {
                        "event": "media",
                        "streamSid": self.ctx.stream_sid,
                        "media": {"payload": base64.b64encode(frame).decode()},
                    }
                )
                # Pace at wall-clock rate. Sending flat out would overrun
                # Twilio's jitter buffer and make barge-in impossible.
                if i % 5 == 4:
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            raise
        finally:
            self.speaking = False
            self._barge_frames = 0

    async def _cancel_playback(self) -> None:
        task, self._playback_task = self._playback_task, None
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.speaking = False

    async def _clear_twilio_buffer(self) -> None:
        """Drop audio Twilio has queued but not yet played."""
        await self.send_json({"event": "clear", "streamSid": self.ctx.stream_sid})

    # -- lifecycle ----------------------------------------------------------

    async def finish(self) -> None:
        """Report the completed call back to the API for analysis."""
        try:
            await self._client.post(
                f"{self.app_base_url}/internal/hangup",
                json={
                    "call_id": self.ctx.call_id,
                    "transcript": self.ctx.full_transcript,
                    "duration_seconds": self.ctx.duration_seconds,
                },
                headers={"X-Internal-Token": self.internal_token},
            )
        except httpx.HTTPError as exc:
            log.error("hangup report failed call_id=%s error=%s", self.ctx.call_id, exc)
