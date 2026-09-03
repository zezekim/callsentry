"""Provider registry: local-first selection with graceful degradation.

Every inference component (STT, LLM, TTS, embeddings) declares a chain:

    local  ->  cloud  ->  mock

`mock` always succeeds. That is deliberate: a failed transcription must never
drop a live call. The caller gets a degraded result and the degradation is
recorded on the call's provider_log so it shows up in the dashboard rather
than disappearing into a stack trace.

Health is cached briefly so a dead local model doesn't add a connection
timeout to every single turn of a conversation.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, TypeVar

import httpx
import structlog

from callsentry.config import Settings, get_settings

log = structlog.get_logger(__name__)

T = TypeVar("T")

_HEALTH_TTL_SECONDS = 30.0
_HEALTH_TIMEOUT_SECONDS = 3.0


class Component(StrEnum):
    STT = "stt"
    LLM = "llm"
    TTS = "tts"
    EMBEDDINGS = "embeddings"
    TELEPHONY = "telephony"
    CALENDAR = "calendar"


class Tier(StrEnum):
    LOCAL = "local"
    CLOUD = "cloud"
    MOCK = "mock"


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    tier: Tier
    component: Component
    # Cost in USD per unit. Local providers are, by construction, 0.00.
    unit: str = "call"
    cost_per_unit: float = 0.0


@dataclass
class ProviderStatus:
    spec: ProviderSpec
    healthy: bool
    detail: str = ""
    checked_at: float = field(default_factory=time.time)


@dataclass
class Attempt:
    """One entry in a call's provider_log."""

    component: str
    provider: str
    tier: str
    ok: bool
    latency_ms: int
    detail: str = ""


# --- Catalogue -------------------------------------------------------------
# cost_per_unit values are list prices as of 2026-07 and are used only for the
# dashboard's cost estimate; actual billing is whatever the vendor invoices.

CATALOGUE: dict[Component, list[ProviderSpec]] = {
    Component.STT: [
        ProviderSpec("whisper.cpp", Tier.LOCAL, Component.STT, unit="audio_minute"),
        ProviderSpec(
            "deepgram", Tier.CLOUD, Component.STT, unit="audio_minute", cost_per_unit=0.0043
        ),
        ProviderSpec("mock-stt", Tier.MOCK, Component.STT, unit="audio_minute"),
    ],
    Component.LLM: [
        ProviderSpec("ollama", Tier.LOCAL, Component.LLM, unit="1k_tokens"),
        # Claude Sonnet 5: $3.00 / MTok in, $15.00 / MTok out. We bill the
        # blended figure per 1k tokens and split in/out in services/llm.py.
        ProviderSpec("claude", Tier.CLOUD, Component.LLM, unit="1k_tokens", cost_per_unit=0.003),
        ProviderSpec("mock-llm", Tier.MOCK, Component.LLM, unit="1k_tokens"),
    ],
    Component.TTS: [
        ProviderSpec("kokoro", Tier.LOCAL, Component.TTS, unit="1k_chars"),
        ProviderSpec("elevenlabs", Tier.CLOUD, Component.TTS, unit="1k_chars", cost_per_unit=0.30),
        ProviderSpec("mock-tts", Tier.MOCK, Component.TTS, unit="1k_chars"),
    ],
    Component.EMBEDDINGS: [
        ProviderSpec("nomic-embed-text", Tier.LOCAL, Component.EMBEDDINGS, unit="1k_tokens"),
        ProviderSpec(
            "openai-embed",
            Tier.CLOUD,
            Component.EMBEDDINGS,
            unit="1k_tokens",
            cost_per_unit=0.00002,
        ),
        ProviderSpec("mock-embed", Tier.MOCK, Component.EMBEDDINGS, unit="1k_tokens"),
    ],
    Component.TELEPHONY: [
        # No local tier exists. A phone number is a physical-world resource.
        ProviderSpec("twilio", Tier.CLOUD, Component.TELEPHONY, unit="minute", cost_per_unit=0.014),
        ProviderSpec("mock-telephony", Tier.MOCK, Component.TELEPHONY, unit="minute"),
    ],
    Component.CALENDAR: [
        ProviderSpec("cal.com", Tier.LOCAL, Component.CALENDAR, unit="booking"),
        ProviderSpec("mock-calendar", Tier.MOCK, Component.CALENDAR, unit="booking"),
    ],
}


class ProviderRegistry:
    """Decides which provider serves each component, and remembers what happened."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._health: dict[str, ProviderStatus] = {}
        self._lock = asyncio.Lock()

    # -- availability -------------------------------------------------------

    def _configured(self, spec: ProviderSpec) -> tuple[bool, str]:
        """Whether a provider is even eligible, before any network check."""
        s = self.settings
        if spec.tier is Tier.MOCK:
            return True, "always available"
        if spec.tier is Tier.CLOUD and spec.component is not Component.TELEPHONY:
            if s.local_only:
                return False, "disabled by local-only mode"
        match spec.name:
            case "deepgram":
                return bool(s.deepgram_api_key), "Deepgram API key not set"
            case "claude":
                return bool(s.claude_api_key), "Claude API key not set"
            case "elevenlabs":
                return bool(s.elevenlabs_api_key), "ElevenLabs API key not set"
            case "openai-embed":
                return bool(s.openai_api_key), "OpenAI API key not set"
            case "twilio":
                return (
                    bool(s.twilio_account_sid and s.twilio_auth_token),
                    "Twilio account SID and auth token not set",
                )
            case "cal.com":
                return bool(s.calcom_api_key), "Cal.com API key not set"
            case _:
                return True, ""

    async def _probe(self, spec: ProviderSpec) -> ProviderStatus:
        """Network health check. Never raises."""
        ok, why = self._configured(spec)
        if not ok:
            return ProviderStatus(spec, False, why)
        if spec.tier is Tier.MOCK:
            return ProviderStatus(spec, True, "mock provider")

        s = self.settings
        url: str | None = None
        match spec.name:
            case "ollama" | "nomic-embed-text":
                url = f"{s.ollama_base_url}/api/tags"
            case "whisper.cpp" | "kokoro":
                url = f"{s.worker_base_url}/health"
            case _:
                # Remote SaaS: treat "configured" as healthy rather than
                # burning a billable request on every health poll.
                return ProviderStatus(spec, True, "configured")

        try:
            async with httpx.AsyncClient(timeout=_HEALTH_TIMEOUT_SECONDS) as client:
                resp = await client.get(url)
            healthy = resp.status_code < 400
            return ProviderStatus(spec, healthy, f"HTTP {resp.status_code}")
        except httpx.HTTPError as exc:
            return ProviderStatus(spec, False, f"unreachable: {type(exc).__name__}")

    def invalidate(self) -> None:
        """Forget cached health so a changed key or URL is re-probed at once."""
        self._health.clear()

    async def status(self, spec: ProviderSpec, *, refresh: bool = False) -> ProviderStatus:
        cached = self._health.get(spec.name)
        fresh = cached and (time.time() - cached.checked_at) < _HEALTH_TTL_SECONDS
        if cached and fresh and not refresh:
            return cached
        async with self._lock:
            status = await self._probe(spec)
            self._health[spec.name] = status
            return status

    async def snapshot(self, *, refresh: bool = False) -> dict[str, list[dict[str, Any]]]:
        """Full provider health map for the /settings/providers dashboard page."""
        out: dict[str, list[dict[str, Any]]] = {}
        for component, specs in CATALOGUE.items():
            rows = []
            for spec in specs:
                st = await self.status(spec, refresh=refresh)
                rows.append(
                    {
                        "provider": spec.name,
                        "tier": spec.tier.value,
                        "healthy": st.healthy,
                        "detail": st.detail,
                        "unit": spec.unit,
                        "cost_per_unit": spec.cost_per_unit,
                    }
                )
            out[component.value] = rows
        return out

    # -- execution ----------------------------------------------------------

    async def run(
        self,
        component: Component,
        handlers: dict[str, Callable[[ProviderSpec], Awaitable[T]]],
        *,
        attempts: list[Attempt] | None = None,
    ) -> tuple[T, ProviderSpec]:
        """Walk the chain for `component`, returning the first successful result.

        `handlers` maps provider name -> coroutine. Providers with no handler
        are skipped. Every attempt (including failures) is appended to
        `attempts` so the call record can show exactly what was tried.
        """
        errors: list[str] = []
        for spec in CATALOGUE[component]:
            handler = handlers.get(spec.name)
            if handler is None:
                continue
            status = await self.status(spec)
            if not status.healthy:
                errors.append(f"{spec.name}: {status.detail}")
                if attempts is not None:
                    attempts.append(
                        Attempt(component, spec.name, spec.tier, False, 0, status.detail)
                    )
                continue

            started = time.perf_counter()
            try:
                result = await handler(spec)
            except Exception as exc:  # noqa: BLE001 - fall through to next tier
                elapsed = int((time.perf_counter() - started) * 1000)
                detail = f"{type(exc).__name__}: {exc}"
                errors.append(f"{spec.name}: {detail}")
                # Mark unhealthy so the rest of this call skips it immediately.
                self._health[spec.name] = ProviderStatus(spec, False, detail)
                if attempts is not None:
                    attempts.append(
                        Attempt(component, spec.name, spec.tier, False, elapsed, detail)
                    )
                log.warning(
                    "provider.failed", component=component, provider=spec.name, error=detail
                )
                continue

            elapsed = int((time.perf_counter() - started) * 1000)
            if attempts is not None:
                attempts.append(Attempt(component, spec.name, spec.tier, True, elapsed))
            return result, spec

        raise ProviderUnavailable(f"no provider served {component.value}: {'; '.join(errors)}")


class ProviderUnavailable(RuntimeError):
    """Raised only when even the mock tier is missing a handler - a wiring bug."""


_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
