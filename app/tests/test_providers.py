"""Provider chain behaviour - the graceful-degradation contract."""

from __future__ import annotations

from callsentry.core.providers import (
    CATALOGUE,
    Attempt,
    Component,
    ProviderRegistry,
    ProviderSpec,
    ProviderStatus,
    Tier,
)


def _spec(component: Component, name: str) -> ProviderSpec:
    return next(s for s in CATALOGUE[component] if s.name == name)


def _force_health(registry: ProviderRegistry, **states: bool) -> None:
    """Pin provider health so tests never touch the network.

    checked_at=inf keeps the entry permanently fresh, so `status()` returns
    the pinned value instead of re-probing.
    """
    by_name = {spec.name: spec for group in CATALOGUE.values() for spec in group}
    for name, healthy in states.items():
        registry._health[name] = ProviderStatus(
            by_name[name], healthy, "forced by test", checked_at=float("inf")
        )


async def test_prefers_local_when_healthy():
    registry = ProviderRegistry()
    _force_health(registry, **{"ollama": True, "claude": True, "mock-llm": True})

    async def local(_: ProviderSpec) -> str:
        return "local"

    async def cloud(_: ProviderSpec) -> str:
        return "cloud"

    async def mock(_: ProviderSpec) -> str:
        return "mock"

    result, spec = await registry.run(
        Component.LLM, {"ollama": local, "claude": cloud, "mock-llm": mock}
    )
    assert result == "local"
    assert spec.tier is Tier.LOCAL


async def test_falls_through_to_cloud_when_local_unhealthy():
    registry = ProviderRegistry()
    _force_health(registry, **{"ollama": False, "claude": True, "mock-llm": True})

    async def cloud(_: ProviderSpec) -> str:
        return "cloud"

    async def mock(_: ProviderSpec) -> str:
        return "mock"

    result, spec = await registry.run(Component.LLM, {"claude": cloud, "mock-llm": mock})
    assert result == "cloud"
    assert spec.tier is Tier.CLOUD


async def test_raising_provider_degrades_rather_than_propagating():
    """A failed transcription must never surface as an exception to the call."""
    registry = ProviderRegistry()
    _force_health(registry, **{"whisper.cpp": True, "deepgram": False, "mock-stt": True})

    async def boom(_: ProviderSpec) -> str:
        raise TimeoutError("model did not respond")

    async def mock(_: ProviderSpec) -> str:
        return "degraded"

    attempts: list[Attempt] = []
    result, spec = await registry.run(
        Component.STT, {"whisper.cpp": boom, "mock-stt": mock}, attempts=attempts
    )

    assert result == "degraded"
    assert spec.tier is Tier.MOCK
    # The failure is recorded, not swallowed silently.
    assert any(a.provider == "whisper.cpp" and not a.ok for a in attempts)
    assert any(a.provider == "mock-stt" and a.ok for a in attempts)


async def test_failed_provider_is_skipped_for_the_rest_of_the_call():
    registry = ProviderRegistry()
    _force_health(registry, **{"ollama": True, "mock-llm": True})
    calls = {"n": 0}

    async def flaky(_: ProviderSpec) -> str:
        calls["n"] += 1
        raise ConnectionError("down")

    async def mock(_: ProviderSpec) -> str:
        return "mock"

    for _ in range(3):
        await registry.run(Component.LLM, {"ollama": flaky, "mock-llm": mock})

    assert calls["n"] == 1, "an already-failed provider should not be retried each turn"


async def test_local_only_blocks_cloud_even_with_keys_present():
    registry = ProviderRegistry()
    registry.settings.callsentry_local_only = True
    registry.settings.claude_api_key = "sk-present"

    ok, reason = registry._configured(_spec(Component.LLM, "claude"))
    assert not ok
    assert "local-only" in reason


async def test_local_only_does_not_block_telephony():
    """There is no local phone number - Twilio must stay reachable."""
    registry = ProviderRegistry()
    registry.settings.callsentry_local_only = True
    registry.settings.twilio_account_sid = "AC123"
    registry.settings.twilio_auth_token = "token"  # noqa: S105 - test fixture

    ok, _ = registry._configured(_spec(Component.TELEPHONY, "twilio"))
    assert ok
