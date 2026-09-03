from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from callsentry.core.db import Base, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from callsentry.models.appointment import Appointment
    from callsentry.models.call import Call
    from callsentry.models.user import User

DEFAULT_HOURS: dict[str, Any] = {
    "mon": ["09:00", "17:00"],
    "tue": ["09:00", "17:00"],
    "wed": ["09:00", "17:00"],
    "thu": ["09:00", "17:00"],
    "fri": ["09:00", "17:00"],
    "sat": None,
    "sun": None,
}


class Business(Base, TimestampMixin):
    """A tenant. Every other row in the system hangs off one of these."""

    __tablename__ = "businesses"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)

    # {"mon": ["09:00","17:00"], ..., "sun": null}. null means closed that day.
    business_hours: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=lambda: dict(DEFAULT_HOURS), nullable=False
    )

    escalation_phone: Mapped[str | None] = mapped_column(String(32))
    after_hours_message: Mapped[str | None] = mapped_column(Text)
    greeting_override: Mapped[str | None] = mapped_column(Text)

    # AES-256-GCM envelopes - never read these directly, use
    # services.credentials.read_credential() which binds business id as AAD.
    cal_com_api_key_enc: Mapped[str | None] = mapped_column(Text)
    cal_com_event_type_id: Mapped[str | None] = mapped_column(String(64))

    twilio_number: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    voice_id: Mapped[str] = mapped_column(String(64), default="af_heart", nullable=False)

    calls: Mapped[list[Call]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    appointments: Mapped[list[Appointment]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
    users: Mapped[list[User]] = relationship(
        back_populates="business", cascade="all, delete-orphan"
    )
