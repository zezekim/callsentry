"""Credential encryption, password hashing, JWTs, and log redaction.

Per-business credentials (Cal.com keys, Twilio subaccount tokens) are stored
encrypted with AES-256-GCM. The ciphertext envelope is:

    b64url( nonce[12] || ciphertext || tag[16] )

with the business id bound in as additional authenticated data, so a
ciphertext copied from one business row into another fails to decrypt.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from typing import Any

import bcrypt
import jwt
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from callsentry.config import get_settings

_NONCE_BYTES = 12
_BCRYPT_ROUNDS = 12


class DecryptionError(RuntimeError):
    """Raised when a stored credential cannot be decrypted or is not authentic."""


def _key() -> bytes:
    raw = base64.urlsafe_b64decode(get_settings().encryption_key)
    if len(raw) != 32:
        raise ValueError("ENCRYPTION_KEY must decode to exactly 32 bytes (AES-256)")
    return raw


def encrypt_secret(plaintext: str, *, aad: str = "") -> str:
    """Encrypt a credential for storage. `aad` should be the owning business id."""
    if not plaintext:
        return ""
    nonce = secrets.token_bytes(_NONCE_BYTES)
    blob = AESGCM(_key()).encrypt(nonce, plaintext.encode(), aad.encode())
    return base64.urlsafe_b64encode(nonce + blob).decode()


def decrypt_secret(envelope: str, *, aad: str = "") -> str:
    """Decrypt a stored credential. Raises DecryptionError on tamper/key mismatch."""
    if not envelope:
        return ""
    try:
        raw = base64.urlsafe_b64decode(envelope)
        nonce, blob = raw[:_NONCE_BYTES], raw[_NONCE_BYTES:]
        return AESGCM(_key()).decrypt(nonce, blob, aad.encode()).decode()
    except (InvalidTag, ValueError, IndexError) as exc:
        raise DecryptionError("stored credential could not be decrypted") from exc


def _prehash(password: str) -> bytes:
    """SHA-256 then base64, so bcrypt always sees exactly 44 bytes.

    Raw bcrypt silently truncates at 72 bytes (and newer bcrypt releases raise
    instead), which would either weaken or break long passphrases. Hashing
    first makes password length irrelevant. Base64 rather than raw digest
    because bcrypt stops at the first NUL byte.
    """
    return base64.b64encode(hashlib.sha256(password.encode("utf-8")).digest())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def verify_password(password: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return bcrypt.checkpw(_prehash(password), hashed.encode())
    except (ValueError, TypeError):
        # Malformed hash in the database - treat as a failed login, not a 500.
        return False


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode(), b.encode())


def issue_token(*, user_id: str, business_id: str, role: str) -> str:
    settings = get_settings()
    now = int(time.time())
    payload = {
        "sub": user_id,
        "biz": business_id,
        "role": role,
        "iat": now,
        "exp": now + settings.jwt_ttl_seconds,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


# --- Log hygiene -----------------------------------------------------------

_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_\-]{8,}|AC[0-9a-fA-F]{30,}|SK[0-9a-fA-F]{30,}|cal_[A-Za-z0-9_\-]{8,})"
)


def mask(value: str | None) -> str:
    """Render a credential safe for logs: keeps a 4-char tail for correlation."""
    if not value:
        return "<unset>"
    if len(value) <= 8:
        return "****"
    return f"****{value[-4:]}"


def scrub(text: str) -> str:
    """Strip anything that looks like an API key out of free-form text."""
    return _SECRET_PATTERN.sub(lambda m: mask(m.group(0)), text)
