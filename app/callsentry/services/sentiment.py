"""Post-call analysis: summary, sentiment, outcome, escalation reason.

Runs off the realtime path, so thinking stays enabled (realtime=False) and
the schema-constrained call gets a proper reasoning budget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from callsentry.models import CallOutcome, Sentiment
from callsentry.services.llm import LLMResult, get_llm

log = structlog.get_logger(__name__)

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "2-3 sentences: what the caller wanted, what was resolved, next action.",
        },
        "sentiment": {"type": "string", "enum": ["positive", "neutral", "negative"]},
        "outcome": {
            "type": "string",
            "enum": ["booked", "answered", "escalated", "voicemail", "abandoned"],
        },
        "escalation_reason": {
            "type": "string",
            "description": "Why a human was needed, or empty string if not escalated.",
        },
        "topics": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Short topic labels for analytics, e.g. 'pricing', 'hours'.",
        },
    },
    "required": ["summary", "sentiment", "outcome", "escalation_reason", "topics"],
    "additionalProperties": False,
}

SYSTEM = """You analyse completed phone call transcripts for a business's AI receptionist.

Rules:
- Summarise only what is in the transcript. Never infer facts that were not said.
- sentiment reflects the CALLER's tone, not the assistant's.
- outcome is 'booked' only if an appointment was actually confirmed.
- outcome is 'escalated' if the caller was transferred or asked for a human.
- outcome is 'abandoned' if the caller hung up mid-conversation.
- If the transcript is empty or unusable, say so plainly in the summary and
  use sentiment 'neutral', outcome 'abandoned'."""


@dataclass
class CallAnalysis:
    summary: str
    sentiment: str
    outcome: str
    escalation_reason: str
    topics: list[str]
    llm: LLMResult


async def analyse(transcript: str, *, business_name: str) -> CallAnalysis:
    if not transcript.strip():
        empty = LLMResult(text="", provider="noop", tier="local")
        return CallAnalysis(
            summary="No transcript was captured for this call.",
            sentiment=Sentiment.NEUTRAL,
            outcome=CallOutcome.ABANDONED,
            escalation_reason="",
            topics=[],
            llm=empty,
        )

    parsed, result = await get_llm().complete_json(
        SYSTEM,
        [
            {
                "role": "user",
                "content": f"Business: {business_name}\n\nTranscript:\n{transcript}",
            }
        ],
        ANALYSIS_SCHEMA,
        realtime=False,
    )

    # A model that returned nothing usable must not produce a bogus "positive
    # / booked" record - fall back to neutral/answered and say why.
    if not parsed:
        return CallAnalysis(
            summary="Automatic analysis was unavailable for this call.",
            sentiment=Sentiment.NEUTRAL,
            outcome=CallOutcome.ANSWERED,
            escalation_reason="",
            topics=[],
            llm=result,
        )

    return CallAnalysis(
        summary=parsed.get("summary", "").strip(),
        sentiment=parsed.get("sentiment", Sentiment.NEUTRAL),
        outcome=parsed.get("outcome", CallOutcome.ANSWERED),
        escalation_reason=parsed.get("escalation_reason", "").strip(),
        topics=[t for t in parsed.get("topics", []) if isinstance(t, str)][:8],
        llm=result,
    )
