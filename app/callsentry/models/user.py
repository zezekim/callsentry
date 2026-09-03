from __future__ import annotations

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from callsentry.core.db import Base, TimestampMixin, uuid_pk

if TYPE_CHECKING:
    from callsentry.models.business import Business


class UserRole(StrEnum):
    ADMIN = "admin"
    OPERATOR = "operator"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = uuid_pk()
    business_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # operator = platform staff, can provision and see cross-tenant costs.
    role: Mapped[str] = mapped_column(String(16), default=UserRole.ADMIN, nullable=False)

    business: Mapped[Business] = relationship(back_populates="users")
