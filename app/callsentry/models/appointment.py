from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from callsentry.core.db import Base, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from callsentry.models.business import Business
    from callsentry.models.call import Call


class AppointmentStatus(StrEnum):
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"
    NO_SHOW = "no_show"


class Appointment(Base, TimestampMixin):
    __tablename__ = "appointments"
    __table_args__ = (Index("ix_appointments_business_scheduled", "business_id", "scheduled_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calls.id", ondelete="SET NULL")
    )

    caller_name: Mapped[str] = mapped_column(String(200), nullable=False)
    caller_phone: Mapped[str] = mapped_column(String(32), nullable=False)
    caller_email: Mapped[str | None] = mapped_column(String(320))
    reason: Mapped[str | None] = mapped_column(Text)

    # Always stored UTC-aware. `timezone` records the caller's local zone so
    # confirmations and reminders render in the time they actually agreed to.
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    status: Mapped[str] = mapped_column(
        String(16), default=AppointmentStatus.CONFIRMED, nullable=False
    )

    # Unique so a Cal.com webhook replay cannot create a duplicate row.
    cal_com_event_id: Mapped[str | None] = mapped_column(String(128), unique=True, index=True)
    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmation_sent: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    business: Mapped[Business] = relationship(back_populates="appointments")
    call: Mapped[Call | None] = relationship(back_populates="appointments")
