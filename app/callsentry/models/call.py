from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from callsentry.core.db import Base, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from callsentry.models.appointment import Appointment
    from callsentry.models.business import Business


class CallOutcome(StrEnum):
    BOOKED = "booked"
    ANSWERED = "answered"
    ESCALATED = "escalated"
    VOICEMAIL = "voicemail"
    ABANDONED = "abandoned"


class Sentiment(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"


class Call(Base, TimestampMixin):
    __tablename__ = "calls"
    __table_args__ = (
        Index("ix_calls_business_created", "business_id", "created_at"),
        Index("ix_calls_business_outcome", "business_id", "outcome"),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )

    # Twilio's CallSid. Unique so webhook retries are idempotent.
    provider_call_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True)
    caller_number: Mapped[str] = mapped_column(String(32), nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    outcome: Mapped[str] = mapped_column(String(16), default=CallOutcome.ANSWERED, nullable=False)
    sentiment: Mapped[str | None] = mapped_column(String(16))

    transcript: Mapped[str | None] = mapped_column(Text)
    summary: Mapped[str | None] = mapped_column(Text)
    recording_url: Mapped[str | None] = mapped_column(Text)
    # Set at ingest to created_at + RECORDING_RETENTION_DAYS. The retention
    # sweep deletes on this column rather than recomputing policy per row, so
    # changing the policy never retroactively deletes existing media.
    recording_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    escalated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    escalation_reason: Mapped[str | None] = mapped_column(Text)

    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0, nullable=False)

    # Append-only list of provider attempts (see core.providers.Attempt).
    # This is what makes "which tier served this call" answerable after the fact.
    provider_log: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, nullable=False
    )

    business: Mapped[Business] = relationship(back_populates="calls")
    appointments: Mapped[list[Appointment]] = relationship(back_populates="call")
