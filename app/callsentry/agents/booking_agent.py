"""Appointment booking: slot resolution, Cal.com booking, SMS confirmation.

Slot times are never invented. `propose` asks Cal.com what is actually free
and offers the nearest real opening; `confirm` books that exact slot. If
Cal.com rejects the booking (someone took it in between), the caller is told
and re-offered rather than being sent a confirmation for a booking that
doesn't exist.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import structlog
from dateutil import parser as date_parser
from sqlalchemy.ext.asyncio import AsyncSession

from callsentry.models import Appointment, AppointmentStatus, Business
from callsentry.services.calcom import BookingResult, CalComError, CalComService, Slot
from callsentry.services.credentials import read_credential
from callsentry.services.sms import get_sms

log = structlog.get_logger(__name__)


@dataclass
class SlotProposal:
    ok: bool
    slot: Slot | None = None
    spoken: str = ""
    error: str = ""


def parse_preferred_time(text: str, *, timezone: str) -> datetime:
    """Best-effort resolution of a caller's spoken time into a datetime.

    Falls back to "tomorrow morning" rather than raising - the proposal step
    then snaps to a real opening anyway, so a bad parse costs one clarifying
    exchange, not a failed call.
    """
    tz = ZoneInfo(timezone)
    now = datetime.now(tz)
    cleaned = (text or "").strip()

    if not cleaned:
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

    try:
        # `default` anchors relative phrases like "Tuesday at 3" to today.
        anchor = now.replace(second=0, microsecond=0)
        parsed = date_parser.parse(cleaned, fuzzy=True, default=anchor)
    except (ValueError, OverflowError):
        return (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    # "Monday at 2" spoken on Tuesday means next Monday, not last one.
    if parsed < now:
        parsed += timedelta(days=7)
    return parsed.astimezone(UTC)


def _service_for(business: Business) -> CalComService:
    return CalComService(
        api_key=read_credential(business, "cal_com_api_key_enc"),
        event_type_id=business.cal_com_event_type_id,
    )


async def propose(business: Business, *, preferred_time: str) -> SlotProposal:
    service = _service_for(business)
    if not service.configured:
        return SlotProposal(False, error="calendar_not_configured")

    wanted = parse_preferred_time(preferred_time, timezone=business.timezone)
    try:
        slot = await service.find_slot(preferred=wanted, timezone=business.timezone)
    except CalComError as exc:
        log.warning("booking.availability_failed", error=str(exc))
        return SlotProposal(False, error="calendar_unavailable")

    if slot is None:
        return SlotProposal(False, error="no_availability")
    return SlotProposal(True, slot=slot, spoken=slot.human(business.timezone))


async def confirm(
    session: AsyncSession,
    business: Business,
    *,
    call_id: uuid.UUID | None,
    slot: Slot,
    name: str,
    phone: str,
    email: str | None,
    reason: str | None,
) -> tuple[bool, Appointment | None, str]:
    """Book the slot, persist it, and text a confirmation."""
    service = _service_for(business)

    # Cal.com requires an email. Use a routable placeholder tied to the phone
    # number so the booking is still traceable back to the caller.
    booking_email = email or f"{phone.lstrip('+') or 'caller'}@callsentry.invalid"

    result: BookingResult = await service.book(
        start=slot.start,
        name=name or "Phone caller",
        email=booking_email,
        phone=phone,
        reason=reason,
        timezone=business.timezone,
    )
    if not result.ok:
        return False, None, "booking_rejected"

    appointment = Appointment(
        business_id=business.id,
        call_id=call_id,
        caller_name=name or "Phone caller",
        caller_phone=phone,
        caller_email=email,
        reason=reason,
        scheduled_at=slot.start,
        timezone=business.timezone,
        status=AppointmentStatus.CONFIRMED,
        cal_com_event_id=result.event_id,
    )
    session.add(appointment)
    await session.flush()

    spoken = slot.human(business.timezone)
    sms = await get_sms().send(
        to=phone,
        body=(
            f"{business.name}: your appointment is confirmed for {spoken}. "
            f"Reply to this message or call us if you need to change it."
        ),
        from_=business.twilio_number,
    )
    appointment.confirmation_sent = sms.sent

    log.info(
        "booking.confirmed",
        appointment_id=str(appointment.id),
        cal_event=result.event_id,
        sms_sent=sms.sent,
    )
    return True, appointment, spoken


async def send_due_reminders(session: AsyncSession) -> int:
    """Text anyone with an appointment 24-48h out who hasn't been reminded."""
    from sqlalchemy import select

    now = datetime.now(UTC)
    window_start, window_end = now + timedelta(hours=23), now + timedelta(hours=25)

    rows = (
        await session.execute(
            select(Appointment, Business)
            .join(Business, Appointment.business_id == Business.id)
            .where(
                Appointment.status == AppointmentStatus.CONFIRMED,
                Appointment.reminder_sent.is_(False),
                Appointment.scheduled_at >= window_start,
                Appointment.scheduled_at <= window_end,
            )
        )
    ).all()

    sent = 0
    for appointment, business in rows:
        spoken = Slot(appointment.scheduled_at, appointment.scheduled_at).human(business.timezone)
        result = await get_sms().send(
            to=appointment.caller_phone,
            body=f"Reminder from {business.name}: your appointment is tomorrow, {spoken}.",
            from_=business.twilio_number,
        )
        if result.sent:
            appointment.reminder_sent = True
            sent += 1
    return sent
