from __future__ import annotations

import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from callsentry.core.db import Base, TimestampMixin, uuid_pk


class CostCategory(StrEnum):
    STT = "stt"
    TTS = "tts"
    LLM = "llm"
    TELEPHONY = "telephony"
    EMBEDDINGS = "embeddings"


class CostEntry(Base, TimestampMixin):
    """One billable (or free) provider interaction.

    Local providers write rows too, with cost_usd = 0. That is the point: the
    dashboard can show "47 inference calls, $0.00" next to "3.2 telephony
    minutes, $0.045" and make the local-first argument concrete.
    """

    __tablename__ = "cost_entries"
    __table_args__ = (Index("ix_cost_entries_business_created", "business_id", "created_at"),)

    id: Mapped[uuid.UUID] = uuid_pk()
    call_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("calls.id", ondelete="CASCADE")
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    tier: Mapped[str] = mapped_column(String(16), default="local", nullable=False)
    units: Mapped[float] = mapped_column(Numeric(12, 4), default=0, nullable=False)
    unit_name: Mapped[str] = mapped_column(String(32), default="call", nullable=False)
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0, nullable=False)
