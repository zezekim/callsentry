from __future__ import annotations

import base64
import os
import secrets

# Settings are read at import time, so the environment must be populated
# before anything under callsentry.* is imported.
os.environ.setdefault("ENCRYPTION_KEY", base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())
os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(32))
os.environ.setdefault("INTERNAL_API_TOKEN", secrets.token_urlsafe(24))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")
os.environ.setdefault("CALLSENTRY_LOCAL_ONLY", "1")

import pytest  # noqa: E402


@pytest.fixture
def business():
    """A minimally-populated Business that needs no database."""
    import uuid

    from callsentry.models import Business

    return Business(
        id=uuid.uuid4(),
        name="Test Clinic",
        timezone="America/New_York",
        business_hours={
            "mon": ["09:00", "17:00"],
            "tue": ["09:00", "17:00"],
            "wed": ["09:00", "17:00"],
            "thu": ["09:00", "17:00"],
            "fri": ["09:00", "17:00"],
            "sat": None,
            "sun": None,
        },
        escalation_phone="+15550001111",
        voice_id="af_heart",
    )
