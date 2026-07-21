"""Speech-to-text: Whisper.cpp (local) -> Deepgram (cloud) -> mock.

Failure isolation rule: a transcription failure must never fail the call. The
mock tier returns an empty transcript with a marker so the dashboard shows
"transcription unavailable" instead of the call record vanishing.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx
import structlog

from callsentry.config import get_settings
from callsentry.core.providers import Attempt, Component, ProviderSpec, get_registry

log = structlog.get_logger(__name__)


@dataclass
class TranscriptResult:
    text: str
    provider: str
    tier: str
    duration_seconds: float = 0.0
    cost_usd: float = 0.0
    attempts: list[Attempt] = field(default_factory=list)


class TranscriptionService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.registry = get_registry()

    async def _via_whisper(self, audio: bytes, filename: str) -> TranscriptResult:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{self.settings.worker_base_url}/stt",
                files={"file": (filename, audio, "audio/wav")},
            )
            resp.raise_for_status()
            data = resp.json()
        return TranscriptResult(
            text=data.get("text", "").strip(),
            provider="whisper.cpp",
            tier="local",
            duration_seconds=float(data.get("duration_seconds", 0.0)),
            cost_usd=0.0,
        )

    async def _via_deepgram(self, audio: bytes) -> TranscriptResult:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "https://api.deepgram.com/v1/listen",
                params={"model": "nova-2", "smart_format": "true", "punctuate": "true"},
                headers={
                    "Authorization": f"Token {self.settings.deepgram_api_key}",
                    "Content-Type": "audio/wav",
                },
                content=audio,
            )
            resp.raise_for_status()
            data = resp.json()

        alt = data["results"]["channels"][0]["alternatives"][0]
        duration = float(data.get("metadata", {}).get("duration", 0.0))
        return TranscriptResult(
            text=alt.get("transcript", "").strip(),
            provider="deepgram",
            tier="cloud",
            duration_seconds=duration,
            cost_usd=round(duration / 60 * 0.0043, 6),
        )

    async def transcribe(self, audio: bytes, *, filename: str = "call.wav") -> TranscriptResult:
        attempts: list[Attempt] = []

        async def whisper(_: ProviderSpec) -> TranscriptResult:
            return await self._via_whisper(audio, filename)

        async def deepgram(_: ProviderSpec) -> TranscriptResult:
            return await self._via_deepgram(audio)

        async def mock(_: ProviderSpec) -> TranscriptResult:
            return TranscriptResult(
                text="[transcription unavailable - no STT provider responded]",
                provider="mock-stt",
                tier="mock",
            )

        result, _ = await self.registry.run(
            Component.STT,
            {"whisper.cpp": whisper, "deepgram": deepgram, "mock-stt": mock},
            attempts=attempts,
        )
        result.attempts = attempts
        return result


_service: TranscriptionService | None = None


def get_transcription() -> TranscriptionService:
    global _service
    if _service is None:
        _service = TranscriptionService()
    return _service
