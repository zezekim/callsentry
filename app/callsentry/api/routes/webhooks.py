"""Inbound webhooks: Twilio voice/SMS and Cal.com booking updates.

Twilio requests are authenticated by HMAC signature, not by obscurity of the
URL. Anyone can POST to a public webhook; without validation they could
fabricate calls, transcripts, and costs against a tenant.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from xml.sax.saxutils import escape

import structlog
from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from callsentry.agents.voice_agent import CallState, is_open, opening_line
from callsentry.api.deps import SessionDep, SettingsDep
from callsentry.models import (
    Appointment,
    AppointmentStatus,
    Business,
    Call,
    CallOutcome,
    CostCategory,
)
from callsentry.services import callstate, costs

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/webhooks", tags=["webhooks"])

TWILIO_PER_MINUTE_USD = 0.014


async def _validate_twilio(request: Request, form: dict[str, Any], settings: Any) -> None:
    """Reject anything not signed by Twilio.

    Skipped only when no auth token is configured at all - i.e. a local demo
    with mock telephony, where there is no signature to check against.
    """
    if not settings.twilio_auth_token:
        log.warning("twilio.signature_check_skipped", reason="no auth token configured")
        return

    from twilio.request_validator import RequestValidator

    signature = request.headers.get("X-Twilio-Signature", "")
    # Twilio signs the URL it dialled, which is the public one - behind Caddy
    # the request URL may say http://app:8000, so rebuild from PUBLIC_BASE_URL.
    url = f"{settings.public_base_url.rstrip('/')}{request.url.path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    validator = RequestValidator(settings.twilio_auth_token)
    if not validator.validate(url, form, signature):
        log.warning("twilio.invalid_signature", url=url)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "invalid Twilio signature")


def _twiml(body: str) -> Response:
    return Response(
        content=f'<?xml version="1.0" encoding="UTF-8"?><Response>{body}</Response>',
        media_type="application/xml",
    )


@router.post("/twilio")
async def twilio_voice(
    request: Request, session: SessionDep, settings: SettingsDep
) -> Response:
    """Inbound call. Answers with a Media Stream pointed at the Pipecat agent."""
    form = dict(await request.form())
    await _validate_twilio(request, form, settings)

    call_sid = str(form.get("CallSid", ""))
    from_number = str(form.get("From", "unknown"))
    to_number = str(form.get("To", ""))

    business = await session.scalar(select(Business).where(Business.twilio_number == to_number))
    if business is None:
        # Fall back to the only tenant in a single-business deployment, which
        # is the common demo case; otherwise we genuinely can't route.
        businesses = (await session.scalars(select(Business).limit(2))).all()
        business = businesses[0] if len(businesses) == 1 else None

    if business is None:
        log.error("twilio.unroutable_number", to=to_number)
        return _twiml(
            "<Say>Sorry, this number is not configured. Goodbye.</Say><Hangup/>"
        )

    # Idempotent: Twilio retries webhooks, and a retry must not create a
    # second call row or a second greeting.
    call = await session.scalar(select(Call).where(Call.provider_call_id == call_sid))
    if call is None:
        call = Call(
            business_id=business.id,
            provider_call_id=call_sid,
            caller_number=from_number,
            outcome=CallOutcome.ANSWERED,
            recording_expires_at=datetime.now(UTC)
            + timedelta(days=settings.recording_retention_days),
            provider_log=[],
        )
        session.add(call)
        await session.flush()

    after_hours = not is_open(business)
    greeting = opening_line(business, after_hours=after_hours)

    await callstate.save(
        CallState(
            call_id=str(call.id),
            business_id=str(business.id),
            caller_number=from_number,
            after_hours=after_hours,
        )
    )

    ws_url = f"{settings.public_ws_url.rstrip('/')}/ws/call/{call.id}"
    log.info(
        "call.started",
        call_id=str(call.id),
        business=business.name,
        after_hours=after_hours,
        stream_url=ws_url,
    )

    # <Connect><Stream> hands the bidirectional audio to Pipecat. The greeting
    # rides along as a parameter so the agent can speak before the caller does.
    return _twiml(
        "<Connect>"
        f'<Stream url="{escape(ws_url)}">'
        f'<Parameter name="callId" value="{call.id}"/>'
        f'<Parameter name="businessId" value="{business.id}"/>'
        f'<Parameter name="greeting" value="{escape(greeting)}"/>'
        f'<Parameter name="voice" value="{escape(business.voice_id)}"/>'
        "</Stream>"
        "</Connect>"
    )


@router.post("/twilio/status")
async def twilio_status(
    request: Request, session: SessionDep, settings: SettingsDep
) -> Response:
    """Call completion callback: duration, recording, and cost settlement."""
    form = dict(await request.form())
    await _validate_twilio(request, form, settings)

    call_sid = str(form.get("CallSid", ""))
    call = await session.scalar(select(Call).where(Call.provider_call_id == call_sid))
    if call is None:
        log.warning("twilio.status_for_unknown_call", call_sid=call_sid)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    duration = int(form.get("CallDuration") or 0)
    call.duration_seconds = duration
    if recording := form.get("RecordingUrl"):
        call.recording_url = str(recording)

    if str(form.get("CallStatus")) in {"no-answer", "busy", "failed", "canceled"}:
        call.outcome = CallOutcome.ABANDONED

    # Telephony is billed per started minute.
    minutes = max(1, -(-duration // 60)) if duration else 0
    if minutes:
        await costs.record(
            session,
            business_id=call.business_id,
            call_id=call.id,
            category=CostCategory.TELEPHONY,
            provider="twilio",
            tier="cloud",
            units=minutes,
            unit_name="minute",
            cost_usd=round(minutes * TWILIO_PER_MINUTE_USD, 6),
        )
    call.cost_usd = await costs.recompute_call_cost(session, call.id)
    await callstate.clear(str(call.id))

    log.info("call.completed", call_id=str(call.id), duration=duration,
             cost_usd=float(call.cost_usd))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/cal")
async def cal_webhook(request: Request, session: SessionDep) -> dict[str, str]:
    """Cal.com booking lifecycle: keep our rows in step with the calendar."""
    payload = await request.json()
    event = payload.get("triggerEvent", "")
    booking = payload.get("payload", {}) or {}
    event_id = str(booking.get("uid") or booking.get("id") or "")

    if not event_id:
        return {"status": "ignored", "reason": "no booking id"}

    appointment = await session.scalar(
        select(Appointment).where(Appointment.cal_com_event_id == event_id)
    )
    if appointment is None:
        # A booking made directly in Cal.com, not through a call. Nothing to
        # reconcile - the calendar remains the source of truth for those.
        return {"status": "ignored", "reason": "unknown booking"}

    match event:
        case "BOOKING_CANCELLED":
            appointment.status = AppointmentStatus.CANCELLED
        case "BOOKING_RESCHEDULED":
            if start := booking.get("startTime"):
                appointment.scheduled_at = datetime.fromisoformat(start.replace("Z", "+00:00"))
                appointment.reminder_sent = False
        case "BOOKING_CREATED" | "BOOKING_CONFIRMED":
            appointment.status = AppointmentStatus.CONFIRMED

    log.info("calcom.webhook", event=event, appointment_id=str(appointment.id))
    return {"status": "ok"}
