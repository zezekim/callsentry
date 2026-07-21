"""Intent classification for a caller utterance.

Schema-constrained so the result is always actionable. On any model failure
the fallback is `escalate` - handing to a human is the safe default when we
don't know what someone wants.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import structlog

from callsentry.services.llm import LLMResult, get_llm

log = structlog.get_logger(__name__)


class Intent(StrEnum):
    BOOKING = "booking"
    FAQ = "faq"
    ESCALATE = "escalate"
    EMERGENCY = "emergency"
    CANCEL = "cancel"
    WRONG_NUMBER = "wrong_number"
    SMALLTALK = "smalltalk"
    GOODBYE = "goodbye"


INTENT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "enum": [i.value for i in Intent],
        },
        "confidence": {"type": "number"},
        "frustrated": {
            "type": "boolean",
            "description": "True if the caller sounds annoyed, angry, or is repeating themselves.",
        },
        "entities": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "email": {"type": "string"},
                "phone": {"type": "string"},
                "preferred_time": {
                    "type": "string",
                    "description": "Natural language time the caller asked for, verbatim.",
                },
                "reason": {"type": "string"},
            },
            "required": ["name", "email", "phone", "preferred_time", "reason"],
            "additionalProperties": False,
        },
    },
    "required": ["intent", "confidence", "frustrated", "entities"],
    "additionalProperties": False,
}

SYSTEM = """You classify a caller's intent for a business phone receptionist.

Intents:
- booking      : wants to make, move, or ask about scheduling an appointment
- faq          : asking a question about the business (hours, services, location, policy)
- escalate     : explicitly asks for a person, a manager, or to be transferred
- emergency    : urgent safety/medical/property situation needing immediate help
- cancel       : wants to cancel or reschedule an existing appointment
- wrong_number : reached the wrong business
- smalltalk    : greeting or pleasantry with no request yet
- goodbye      : ending the call

Set `frustrated` true when the caller repeats themselves, raises objections,
or expresses annoyance - this triggers an offer to transfer.

Leave any entity you did not hear as an empty string. Never guess a name,
email, or phone number. `preferred_time` is the caller's own words, not a
resolved date."""


@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    frustrated: bool
    entities: dict[str, str]
    llm: LLMResult


async def detect(utterance: str, *, history: list[dict[str, str]] | None = None) -> IntentResult:
    messages = list(history or [])
    messages.append({"role": "user", "content": utterance})

    parsed, result = await get_llm().complete_json(SYSTEM, messages, INTENT_SCHEMA, realtime=True)

    if not parsed or "intent" not in parsed:
        log.warning("intent.fallback_to_escalate", provider=result.provider)
        return IntentResult(Intent.ESCALATE, 0.0, False, _empty_entities(), result)

    try:
        intent = Intent(parsed["intent"])
    except ValueError:
        intent = Intent.ESCALATE

    entities = {**_empty_entities(), **(parsed.get("entities") or {})}
    return IntentResult(
        intent=intent,
        confidence=float(parsed.get("confidence", 0.0)),
        frustrated=bool(parsed.get("frustrated", False)),
        entities={k: str(v or "").strip() for k, v in entities.items()},
        llm=result,
    )


def _empty_entities() -> dict[str, str]:
    return {"name": "", "email": "", "phone": "", "preferred_time": "", "reason": ""}
