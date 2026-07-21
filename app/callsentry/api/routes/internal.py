"""Endpoints consumed only by the Pipecat voice container.

Guarded by INTERNAL_API_TOKEN. These are not part of the public API surface
and are excluded from the OpenAPI schema.
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from callsentry.agents import voice_agent
from callsentry.api.deps import InternalDep, SessionDep
from callsentry.models import Business, Call, CallOutcome
from callsentry.services import callstate

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


class TurnRequest(BaseModel):
    call_id: str
    utterance: str


class TurnResponseOut(BaseModel):
    text: str
    end_call: bool = False
    transfer_to: str | None = None
    voice: str = "af_heart"


class HangupRequest(BaseModel):
    call_id: str
    transcript: str = ""
    duration_seconds: int = 0


async def _load(session: SessionDep, call_id: str) -> tuple[Call, Business]:
    try:
        parsed = uuid.UUID(call_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "malformed call id") from exc

    call = await session.get(Call, parsed)
    if call is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "call not found")
    business = await session.get(Business, call.business_id)
    if business is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "business not found")
    return call, business


@router.post("/turn", response_model=TurnResponseOut)
async def turn(
    payload: TurnRequest, session: SessionDep, _: InternalDep
) -> TurnResponseOut:
    """One caller utterance in, one thing to say out."""
    call, business = await _load(session, payload.call_id)

    state = await callstate.load(payload.call_id)
    if state is None:
        # State expired or the app restarted mid-call. Rebuild rather than
        # dropping the caller; they lose context, not the call.
        state = voice_agent.CallState(
            call_id=payload.call_id,
            business_id=str(business.id),
            caller_number=call.caller_number,
            after_hours=not voice_agent.is_open(business),
        )

    result = await voice_agent.handle_turn(
        session, business=business, call=call, state=state, utterance=payload.utterance
    )

    if result.outcome:
        call.outcome = result.outcome
    if result.escalation_reason:
        call.escalated = True
        call.escalation_reason = result.escalation_reason

    await callstate.save(state)

    return TurnResponseOut(
        text=result.text,
        end_call=result.end_call,
        transfer_to=result.transfer_to,
        voice=business.voice_id,
    )


@router.post("/hangup", status_code=status.HTTP_204_NO_CONTENT)
async def hangup(payload: HangupRequest, session: SessionDep, _: InternalDep) -> None:
    """Call ended: run post-call analysis and settle costs."""
    call, business = await _load(session, payload.call_id)

    if payload.duration_seconds:
        call.duration_seconds = payload.duration_seconds
    if call.outcome == CallOutcome.ANSWERED and not payload.transcript.strip():
        call.outcome = CallOutcome.ABANDONED

    await voice_agent.finalize_call(
        session, call=call, business=business, transcript=payload.transcript
    )
    await callstate.clear(payload.call_id)


@router.get("/call/{call_id}/context")
async def call_context(call_id: str, session: SessionDep, _: InternalDep) -> dict[str, str | bool]:
    """Everything Pipecat needs to open the session: greeting, voice, hours."""
    call, business = await _load(session, call_id)
    after_hours = not voice_agent.is_open(business)
    return {
        "business_name": business.name,
        "greeting": voice_agent.opening_line(business, after_hours=after_hours),
        "voice": business.voice_id,
        "after_hours": after_hours,
        "caller_number": call.caller_number,
    }
