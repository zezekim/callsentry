"""LLM access with a local-first provider chain.

Local  : Ollama (llama3.2)      - free, runs on your box
Cloud  : Claude Sonnet 5        - paid fallback, only when LOCAL_ONLY=0
Mock   : canned safe responses  - so a dead model never drops a live call

Latency notes for the realtime voice path
-----------------------------------------
Claude Sonnet 5 runs *adaptive thinking by default* when the `thinking` field
is omitted. On a phone call that is the wrong trade: thinking tokens are
generated before any text, which shows up to the caller as dead air. Every
realtime turn therefore passes `thinking={"type": "disabled"}` explicitly and
`effort: "low"`. Offline work (summaries, sentiment) leaves thinking on.

Sonnet 5 also rejects non-default `temperature`/`top_p`/`top_k` with a 400 -
do not add them back. Steer tone through the system prompt instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from callsentry.config import get_settings
from callsentry.core.providers import Attempt, Component, ProviderSpec, get_registry

log = structlog.get_logger(__name__)

# Claude Sonnet 5 list pricing, USD per million tokens.
CLAUDE_INPUT_PER_MTOK = 3.00
CLAUDE_OUTPUT_PER_MTOK = 15.00

# Hard ceiling on a spoken turn. Roughly 45 seconds of speech - long enough
# for a real answer, short enough that a runaway generation cannot monologue
# at a caller.
REALTIME_MAX_TOKENS = 300
OFFLINE_MAX_TOKENS = 1024


@dataclass
class LLMResult:
    text: str
    provider: str
    tier: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    refused: bool = False
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.registry = get_registry()
        self._anthropic: Any = None

    def _claude(self) -> Any:
        if self._anthropic is None:
            from anthropic import AsyncAnthropic

            self._anthropic = AsyncAnthropic(api_key=self.settings.claude_api_key)
        return self._anthropic

    # -- providers ----------------------------------------------------------

    async def _via_ollama(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        json_schema: dict[str, Any] | None,
    ) -> LLMResult:
        payload: dict[str, Any] = {
            "model": self.settings.ollama_model,
            "messages": [{"role": "system", "content": system}, *messages],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if json_schema is not None:
            # Ollama constrains generation to a JSON schema when given one.
            payload["format"] = json_schema

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(f"{self.settings.ollama_base_url}/api/chat", json=payload)
            resp.raise_for_status()
            data = resp.json()

        return LLMResult(
            text=data.get("message", {}).get("content", "").strip(),
            provider="ollama",
            tier="local",
            input_tokens=data.get("prompt_eval_count", 0),
            output_tokens=data.get("eval_count", 0),
            cost_usd=0.0,
        )

    async def _via_claude(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        max_tokens: int,
        json_schema: dict[str, Any] | None,
        realtime: bool,
    ) -> LLMResult:
        kwargs: dict[str, Any] = {
            "model": self.settings.claude_model,
            "max_tokens": max_tokens,
            # Cache the system prompt: it carries the business persona and,
            # for KB answers, the retrieved chunks. Identical across turns of
            # a call, so every turn after the first reads at ~0.1x.
            "system": [
                {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": messages,
        }

        if realtime:
            # See module docstring: thinking must be off on the voice path.
            kwargs["thinking"] = {"type": "disabled"}
            kwargs["output_config"] = {"effort": "low"}
        else:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": "medium"}

        if json_schema is not None:
            cfg = kwargs.setdefault("output_config", {})
            cfg["format"] = {"type": "json_schema", "schema": json_schema}

        resp = await self._claude().messages.create(**kwargs)

        # Sonnet 5 can decline via a 200 with stop_reason "refusal"; content
        # is empty or partial. Check before touching content[0].
        if resp.stop_reason == "refusal":
            log.warning("llm.claude_refused", category=getattr(resp.stop_details, "category", None))
            return LLMResult(
                text="",
                provider="claude",
                tier="cloud",
                input_tokens=resp.usage.input_tokens,
                output_tokens=resp.usage.output_tokens,
                refused=True,
            )

        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        cost = (
            resp.usage.input_tokens / 1_000_000 * CLAUDE_INPUT_PER_MTOK
            + resp.usage.output_tokens / 1_000_000 * CLAUDE_OUTPUT_PER_MTOK
        )
        return LLMResult(
            text=text,
            provider="claude",
            tier="cloud",
            input_tokens=resp.usage.input_tokens,
            output_tokens=resp.usage.output_tokens,
            cost_usd=round(cost, 6),
        )

    async def _via_mock(self, json_schema: dict[str, Any] | None) -> LLMResult:
        # The mock must return something the caller can act on. For schema
        # requests that means a valid-but-neutral object; for prose it means
        # a line that hands off to a human rather than inventing an answer.
        if json_schema is not None:
            text = json.dumps(
                {"intent": "escalate", "confidence": 0.0, "reason": "llm_unavailable"}
            )
        else:
            text = (
                "I'm having trouble with that right now. "
                "Let me take a message and have someone call you back."
            )
        return LLMResult(text=text, provider="mock-llm", tier="mock")

    # -- public -------------------------------------------------------------

    async def complete(
        self,
        system: str,
        messages: list[dict[str, str]],
        *,
        realtime: bool = True,
        max_tokens: int | None = None,
        json_schema: dict[str, Any] | None = None,
    ) -> LLMResult:
        """Run one completion through the provider chain.

        `realtime=True` tunes for a live phone turn (no thinking, low effort,
        short output). Set it False for post-call summarisation.
        """
        limit = max_tokens or (REALTIME_MAX_TOKENS if realtime else OFFLINE_MAX_TOKENS)
        attempts: list[Attempt] = []

        async def ollama(_: ProviderSpec) -> LLMResult:
            return await self._via_ollama(
                system, messages, max_tokens=limit, json_schema=json_schema
            )

        async def claude(_: ProviderSpec) -> LLMResult:
            return await self._via_claude(
                system, messages, max_tokens=limit, json_schema=json_schema, realtime=realtime
            )

        async def mock(_: ProviderSpec) -> LLMResult:
            return await self._via_mock(json_schema)

        result, _spec = await self.registry.run(
            Component.LLM,
            {"ollama": ollama, "claude": claude, "mock-llm": mock},
            attempts=attempts,
        )
        result.attempts = attempts
        return result

    async def complete_json(
        self,
        system: str,
        messages: list[dict[str, str]],
        schema: dict[str, Any],
        *,
        realtime: bool = True,
    ) -> tuple[dict[str, Any], LLMResult]:
        """Completion constrained to a JSON schema, with a parse-failure guard."""
        result = await self.complete(
            system, messages, realtime=realtime, json_schema=schema, max_tokens=512
        )
        try:
            parsed = json.loads(result.text)
            if not isinstance(parsed, dict):
                raise ValueError("expected a JSON object")
            return parsed, result
        except (json.JSONDecodeError, ValueError) as exc:
            # A model that ignored the schema is a soft failure, not a crash.
            log.warning("llm.json_parse_failed", provider=result.provider, error=str(exc))
            return {}, result


_service: LLMService | None = None


def get_llm() -> LLMService:
    global _service
    if _service is None:
        _service = LLMService()
    return _service
