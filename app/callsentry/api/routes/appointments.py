from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select

from callsentry.api.deps import BusinessDep, SessionDep
from callsentry.models import Appointment, AppointmentStatus
from callsentry.services.calcom import CalComService
from callsentry.services.credentials import read_credential

router = APIRouter(prefix="/appointments", tags=["appointments"])


class AppointmentOut(BaseModel):
    id: str
    call_id: str | None
    caller_name: str
    caller_phone: str
    caller_email: str | None
    reason: str | None
    scheduled_at: datetime
    timezone: str
    status: str
    cal_com_event_id: str | None
    reminder_sent: bool
    confirmation_sent: bool
    created_at: datetime


class StatusUpdate(BaseModel):
    status: AppointmentStatus


def _out(a: Appointment) -> AppointmentOut:
    return AppointmentOut(
        id=str(a.id),
        call_id=str(a.call_id) if a.call_id else None,
        caller_name=a.caller_name,
        caller_phone=a.caller_phone,
        caller_email=a.caller_email,
        reason=a.reason,
        scheduled_at=a.scheduled_at,
        timezone=a.timezone,
        status=a.status,
        cal_com_event_id=a.cal_com_event_id,
        reminder_sent=a.reminder_sent,
        confirmation_sent=a.confirmation_sent,
        created_at=a.created_at,
    )


@router.get("", response_model=list[AppointmentOut])
async def list_appointments(
    session: SessionDep,
    business: BusinessDep,
    status_filter: str | None = None,
    limit: int = 100,
) -> list[AppointmentOut]:
    stmt = select(Appointment).where(Appointment.business_id == business.id)
    if status_filter:
        stmt = stmt.where(Appointment.status == status_filter)
    stmt = stmt.order_by(Appointment.scheduled_at.desc()).limit(limit)
    rows = (await session.scalars(stmt)).all()
    return [_out(a) for a in rows]


@router.get("/calendar", response_model=list[AppointmentOut])
async def calendar(
    session: SessionDep,
    business: BusinessDep,
    start: datetime | None = None,
    end: datetime | None = None,
) -> list[AppointmentOut]:
    window_start = start or datetime.now(UTC) - timedelta(days=7)
    window_end = end or window_start + timedelta(days=60)
    rows = (
        await session.scalars(
            select(Appointment)
            .where(
                Appointment.business_id == business.id,
                Appointment.scheduled_at >= window_start,
                Appointment.scheduled_at <= window_end,
            )
            .order_by(Appointment.scheduled_at)
        )
    ).all()
    return [_out(a) for a in rows]


@router.patch("/{appointment_id}/status", response_model=AppointmentOut)
async def update_status(
    appointment_id: uuid.UUID,
    payload: StatusUpdate,
    session: SessionDep,
    business: BusinessDep,
) -> AppointmentOut:
    appointment = await session.get(Appointment, appointment_id)
    if appointment is None or appointment.business_id != business.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "appointment not found")

    # Cancelling here must also free the slot in Cal.com, or the calendar and
    # the dashboard disagree about what's available.
    if (
        payload.status is AppointmentStatus.CANCELLED
        and appointment.status != AppointmentStatus.CANCELLED
        and appointment.cal_com_event_id
    ):
        service = CalComService(
            api_key=read_credential(business, "cal_com_api_key_enc"),
            event_type_id=business.cal_com_event_type_id,
        )
        await service.cancel(appointment.cal_com_event_id, reason="Cancelled from dashboard")

    appointment.status = payload.status
    await session.flush()
    return _out(appointment)
