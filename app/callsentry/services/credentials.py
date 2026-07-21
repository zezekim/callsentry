"""Read/write per-business encrypted credentials.

Always goes through here rather than touching the `*_enc` columns directly,
because the business id has to be bound in as AES-GCM additional authenticated
data on both sides. A ciphertext moved between rows fails to decrypt instead
of silently authenticating the wrong tenant's calendar.
"""

from __future__ import annotations

import structlog

from callsentry.config import get_settings
from callsentry.core.security import DecryptionError, decrypt_secret, encrypt_secret
from callsentry.models import Business

log = structlog.get_logger(__name__)

_PLATFORM_FALLBACK = {"cal_com_api_key_enc": "calcom_api_key"}


def write_credential(business: Business, field: str, plaintext: str) -> None:
    setattr(business, field, encrypt_secret(plaintext, aad=str(business.id)))


def read_credential(business: Business, field: str) -> str:
    """Decrypt a business credential, falling back to the platform-wide key."""
    envelope = getattr(business, field, "") or ""
    if envelope:
        try:
            return decrypt_secret(envelope, aad=str(business.id))
        except DecryptionError:
            # Wrong ENCRYPTION_KEY or a tampered row. Log without the value
            # and fall through - better a degraded provider than a 500.
            log.error("credentials.decrypt_failed", business_id=str(business.id), field=field)

    platform_attr = _PLATFORM_FALLBACK.get(field)
    if platform_attr:
        return str(getattr(get_settings(), platform_attr, "") or "")
    return ""


def has_credential(business: Business, field: str) -> bool:
    return bool(read_credential(business, field))
