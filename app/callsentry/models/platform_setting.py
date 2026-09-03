from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from callsentry.core.db import Base


class PlatformSetting(Base):
    """A dashboard-set override for one field of `callsentry.config.Settings`.

    The environment is still the baseline; a row here wins over it until the
    row is deleted. Secret values are AES-GCM envelopes (see
    `services/platform_settings.py`) - never read `value` directly for those.
    """

    __tablename__ = "platform_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
