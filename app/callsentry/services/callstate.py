"""Redis-backed conversation state.

Call state has to survive between HTTP turns and across app replicas, but it
is worthless once the call ends - hence Redis with a TTL rather than a table.
The TTL also bounds the damage from a call that never sends a hangup webhook.
"""

from __future__ import annotations

import json
from datetime import datetime

import redis.asyncio as aioredis
import structlog

from callsentry.agents.voice_agent import CallState
from callsentry.config import get_settings
from callsentry.services.calcom import Slot

log = structlog.get_logger(__name__)

STATE_TTL_SECONDS = 60 * 60  # An hour is far longer than any real call.

_client: aioredis.Redis | None = None


def _redis() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


def _key(call_id: str) -> str:
    return f"callsentry:state:{call_id}"


def _dump(state: CallState) -> str:
    payload = {
        "call_id": state.call_id,
        "business_id": state.business_id,
        "caller_number": state.caller_number,
        "history": state.history,
        "clarifying_questions": state.clarifying_questions,
        "collected": state.collected,
        "after_hours": state.after_hours,
        "turns": state.turns,
        "pending_slot": (
            {
                "start": state.pending_slot.start.isoformat(),
                "end": state.pending_slot.end.isoformat(),
            }
            if state.pending_slot
            else None
        ),
    }
    return json.dumps(payload)


def _load(raw: str) -> CallState:
    data = json.loads(raw)
    slot_data = data.pop("pending_slot", None)
    state = CallState(**data)
    if slot_data:
        state.pending_slot = Slot(
            start=datetime.fromisoformat(slot_data["start"]),
            end=datetime.fromisoformat(slot_data["end"]),
        )
    return state


async def load(call_id: str) -> CallState | None:
    raw = await _redis().get(_key(call_id))
    if raw is None:
        return None
    try:
        return _load(raw)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        # A state blob written by an older build. Dropping it restarts the
        # conversation cleanly rather than 500-ing mid-call.
        log.warning("callstate.corrupt", call_id=call_id, error=str(exc))
        return None


async def save(state: CallState) -> None:
    await _redis().set(_key(state.call_id), _dump(state), ex=STATE_TTL_SECONDS)


async def clear(call_id: str) -> None:
    await _redis().delete(_key(call_id))
