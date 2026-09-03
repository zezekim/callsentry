"""Runtime-editable platform configuration.

`Settings` is built from the environment once at boot. Operators can override
a curated subset from the dashboard. Overrides live in `platform_settings`
(secrets are AES-GCM envelopes bound to a fixed AAD so they can't be replayed
as a tenant credential) and are overlaid onto the cached `Settings` instance,
so every service that reads `get_settings().<field>` at call time sees the new
value without a restart.

Not everything is exposed. Database and Redis URLs, the encryption key, the
JWT secret, and the internal token are boot-time infrastructure: changing them
from a web form would either lock the operator out or silently corrupt stored
credentials.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from callsentry.config import get_settings
from callsentry.core.providers import get_registry
from callsentry.core.security import DecryptionError, decrypt_secret, encrypt_secret, mask
from callsentry.models import PlatformSetting

log = structlog.get_logger(__name__)

# Bound in as AES-GCM AAD. Distinct from every business id, so a platform
# envelope pasted into a business row (or vice versa) fails to decrypt.
_AAD = "platform"

Kind = Literal["text", "secret", "bool", "int", "float", "url"]


@dataclass(frozen=True)
class FieldSpec:
    key: str
    env: str
    group: str
    label: str
    kind: Kind
    help: str = ""
    # True when the value is only read at process start (CORS origins, log
    # configuration). The UI says so next to the field.
    restart: bool = False


FIELDS: tuple[FieldSpec, ...] = (
    FieldSpec(
        "callsentry_local_only",
        "CALLSENTRY_LOCAL_ONLY",
        "mode",
        "Local-only mode",
        "bool",
        "When on, no paid inference API is ever called, whatever keys are configured. "
        "Telephony is exempt because there is no local phone network.",
    ),
    FieldSpec(
        "twilio_account_sid",
        "TWILIO_ACCOUNT_SID",
        "telephony",
        "Twilio account SID",
        "text",
        "Starts with AC. Found on the Twilio console home page.",
    ),
    FieldSpec(
        "twilio_auth_token",
        "TWILIO_AUTH_TOKEN",
        "telephony",
        "Twilio auth token",
        "secret",
        "Used to verify webhook signatures and to send confirmation SMS.",
    ),
    FieldSpec(
        "twilio_phone_number",
        "TWILIO_PHONE_NUMBER",
        "telephony",
        "Default sending number",
        "text",
        "E.164 format. SMS is sent from this number when a business has no number of its own.",
    ),
    FieldSpec(
        "claude_api_key",
        "CLAUDE_API_KEY",
        "llm",
        "Claude API key",
        "secret",
        "Cloud fallback for the language model. Ignored in local-only mode.",
    ),
    FieldSpec(
        "claude_model",
        "CLAUDE_MODEL",
        "llm",
        "Claude model",
        "text",
        "Model identifier used for the cloud fallback.",
    ),
    FieldSpec(
        "ollama_base_url",
        "OLLAMA_BASE_URL",
        "llm",
        "Ollama URL",
        "url",
        "Where the local language model and embedding server listens.",
    ),
    FieldSpec(
        "ollama_model",
        "OLLAMA_MODEL",
        "llm",
        "Ollama model",
        "text",
        "Must already be pulled on the Ollama host.",
    ),
    FieldSpec(
        "deepgram_api_key",
        "DEEPGRAM_API_KEY",
        "speech",
        "Deepgram API key",
        "secret",
        "Cloud fallback for speech to text.",
    ),
    FieldSpec(
        "elevenlabs_api_key",
        "ELEVENLABS_API_KEY",
        "speech",
        "ElevenLabs API key",
        "secret",
        "Cloud fallback for text to speech.",
    ),
    FieldSpec(
        "worker_base_url",
        "WORKER_BASE_URL",
        "speech",
        "Worker URL",
        "url",
        "The local whisper.cpp and Kokoro service.",
    ),
    FieldSpec(
        "retell_api_key",
        "RETELL_API_KEY",
        "speech",
        "Retell API key",
        "secret",
        "Accepted for configuration parity. No current provider chain uses it.",
    ),
    FieldSpec(
        "openai_api_key",
        "OPENAI_API_KEY",
        "embeddings",
        "OpenAI API key",
        "secret",
        "Cloud fallback for knowledge base embeddings.",
    ),
    FieldSpec(
        "ollama_embed_model",
        "OLLAMA_EMBED_MODEL",
        "embeddings",
        "Embedding model",
        "text",
        "Changing to a model with a different vector size requires a migration and "
        "re-indexing every document. Leave as nomic-embed-text unless you have planned that.",
    ),
    FieldSpec(
        "calcom_api_key",
        "CALCOM_API_KEY",
        "calendar",
        "Cal.com platform API key",
        "secret",
        "Used for any business that has not connected its own Cal.com key.",
    ),
    FieldSpec(
        "calcom_base_url",
        "CALCOM_BASE_URL",
        "calendar",
        "Cal.com API URL",
        "url",
        "Point at a self-hosted Cal.com to keep bookings on your own infrastructure.",
    ),
    FieldSpec(
        "kb_confidence_threshold",
        "KB_CONFIDENCE_THRESHOLD",
        "conversation",
        "Knowledge base confidence threshold",
        "float",
        "Between 0 and 1. Below this similarity score the receptionist escalates "
        "rather than answering.",
    ),
    FieldSpec(
        "max_clarifying_questions",
        "MAX_CLARIFYING_QUESTIONS",
        "conversation",
        "Maximum clarifying questions",
        "int",
        "After this many follow-ups on one turn the call is handed to a person.",
    ),
    FieldSpec(
        "recording_retention_days",
        "RECORDING_RETENTION_DAYS",
        "retention",
        "Recording retention (days)",
        "int",
        "Recordings older than this are deleted by the retention sweep.",
    ),
    FieldSpec(
        "transcript_retention_days",
        "TRANSCRIPT_RETENTION_DAYS",
        "retention",
        "Transcript retention (days)",
        "int",
        "Transcripts and summaries older than this are removed.",
    ),
    FieldSpec(
        "jwt_ttl_seconds",
        "JWT_TTL_SECONDS",
        "access",
        "Session length (seconds)",
        "int",
        "How long a dashboard sign-in lasts before the user must sign in again.",
    ),
    FieldSpec(
        "public_base_url",
        "PUBLIC_BASE_URL",
        "urls",
        "Public API URL",
        "url",
        "What Twilio is told to call for webhooks. Must match the URL Twilio actually "
        "hits, or signature checks fail.",
        restart=True,
    ),
    FieldSpec(
        "public_ws_url",
        "PUBLIC_WS_URL",
        "urls",
        "Public media stream URL",
        "url",
        "The wss:// address Twilio streams call audio to.",
    ),
    FieldSpec(
        "log_level",
        "LOG_LEVEL",
        "logging",
        "Log level",
        "text",
        "DEBUG, INFO, WARNING or ERROR.",
        restart=True,
    ),
)

BY_KEY: dict[str, FieldSpec] = {f.key: f for f in FIELDS}

GROUPS: tuple[tuple[str, str], ...] = (
    ("mode", "Operating mode"),
    ("telephony", "Telephony (Twilio)"),
    ("llm", "Language model"),
    ("speech", "Speech"),
    ("embeddings", "Embeddings"),
    ("calendar", "Calendar"),
    ("conversation", "Conversation"),
    ("retention", "Data retention"),
    ("access", "Access"),
    ("urls", "Public URLs"),
    ("logging", "Logging"),
)


class SettingsValidationError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


# --- Coercion ----------------------------------------------------------------

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def coerce(spec: FieldSpec, raw: str) -> Any:
    """Parse a submitted string into the type `Settings` expects. Raises ValueError."""
    text = raw.strip()
    match spec.kind:
        case "bool":
            lowered = text.lower()
            if lowered in _TRUE:
                return True
            if lowered in _FALSE:
                return False
            raise ValueError("must be true or false")
        case "int":
            try:
                value = int(text)
            except ValueError as exc:
                raise ValueError("must be a whole number") from exc
            if value < 0:
                raise ValueError("must not be negative")
            return value
        case "float":
            try:
                number = float(text)
            except ValueError as exc:
                raise ValueError("must be a number") from exc
            if spec.key == "kb_confidence_threshold" and not 0.0 <= number <= 1.0:
                raise ValueError("must be between 0 and 1")
            return number
        case "url":
            if not text.startswith(("http://", "https://", "ws://", "wss://")):
                raise ValueError("must start with http://, https://, ws:// or wss://")
            return text.rstrip("/")
        case "text" | "secret":
            if spec.key == "log_level" and text.upper() not in {
                "DEBUG",
                "INFO",
                "WARNING",
                "ERROR",
            }:
                raise ValueError("must be DEBUG, INFO, WARNING or ERROR")
            if spec.key == "twilio_account_sid" and not text.startswith("AC"):
                raise ValueError("must start with AC")
            return text.upper() if spec.key == "log_level" else text
    raise ValueError("unsupported field")  # pragma: no cover - exhaustive match


def serialize(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


# --- Overlay -----------------------------------------------------------------

# The environment-derived values, captured before any override is applied so
# that clearing an override restores exactly what the process booted with.
_baseline: dict[str, Any] = {}


def _ensure_baseline() -> None:
    if not _baseline:
        settings = get_settings()
        for spec in FIELDS:
            _baseline[spec.key] = getattr(settings, spec.key)


def baseline(key: str) -> Any:
    _ensure_baseline()
    return _baseline[key]


def _stored_to_plain(spec: FieldSpec, row: PlatformSetting) -> str | None:
    if not spec.kind == "secret":
        return row.value
    try:
        return decrypt_secret(row.value, aad=_AAD)
    except DecryptionError:
        # Wrong ENCRYPTION_KEY or a tampered row. Fall back to the environment
        # rather than serving a garbage key to a provider.
        log.error("platform_settings.decrypt_failed", key=spec.key)
        return None


async def _rows(session: AsyncSession) -> dict[str, PlatformSetting]:
    result = await session.scalars(select(PlatformSetting))
    return {row.key: row for row in result}


async def load_overrides(session: AsyncSession) -> int:
    """Apply every stored override to the live Settings. Returns how many applied."""
    _ensure_baseline()
    settings = get_settings()
    applied = 0
    for key, row in (await _rows(session)).items():
        spec = BY_KEY.get(key)
        if spec is None:
            log.warning("platform_settings.unknown_key", key=key)
            continue
        plain = _stored_to_plain(spec, row)
        if plain is None:
            continue
        try:
            setattr(settings, spec.key, coerce(spec, plain))
            applied += 1
        except ValueError as exc:
            log.error("platform_settings.invalid_row", key=key, error=str(exc))
    return applied


async def update(session: AsyncSession, values: dict[str, str | None]) -> None:
    """Validate then persist a batch of overrides. All-or-nothing.

    A `None` or empty string clears the override and restores the environment
    value. Secrets are encrypted before they touch the session.
    """
    _ensure_baseline()
    settings = get_settings()

    errors: dict[str, str] = {}
    parsed: dict[str, Any] = {}
    for key, raw in values.items():
        spec = BY_KEY.get(key)
        if spec is None:
            errors[key] = "unknown setting"
            continue
        if raw is None or not raw.strip():
            parsed[key] = None
            continue
        try:
            parsed[key] = coerce(spec, raw)
        except ValueError as exc:
            errors[key] = str(exc)
    if errors:
        raise SettingsValidationError(errors)

    rows = await _rows(session)
    for key, value in parsed.items():
        spec = BY_KEY[key]
        row = rows.get(key)
        if value is None:
            if row is not None:
                await session.delete(row)
            setattr(settings, key, _baseline[key])
            log.info("platform_settings.cleared", key=key)
            continue

        stored = serialize(value)
        if spec.kind == "secret":
            stored = encrypt_secret(stored, aad=_AAD)
        if row is None:
            session.add(PlatformSetting(key=key, value=stored, is_secret=spec.kind == "secret"))
        else:
            row.value = stored
            row.is_secret = spec.kind == "secret"
        setattr(settings, key, value)
        log.info("platform_settings.updated", key=key, secret=spec.kind == "secret")

    await session.flush()
    # A new key or URL changes which providers are eligible; re-probe now
    # rather than serving a stale "not configured" for the next 30 seconds.
    get_registry().invalidate()


# --- Presentation ------------------------------------------------------------


def _display(spec: FieldSpec, value: Any) -> str:
    text = serialize(value) if value is not None and value != "" else ""
    if spec.kind == "secret":
        return mask(text) if text else ""
    return text


async def describe(session: AsyncSession) -> list[dict[str, Any]]:
    """Every editable field with its current effective value, for the dashboard."""
    _ensure_baseline()
    settings = get_settings()
    rows = await _rows(session)
    out: list[dict[str, Any]] = []
    for spec in FIELDS:
        row = rows.get(spec.key)
        updated: datetime | None = row.updated_at if row else None
        out.append(
            {
                "key": spec.key,
                "env": spec.env,
                "group": spec.group,
                "label": spec.label,
                "kind": spec.kind,
                "help": spec.help,
                "restart_required": spec.restart,
                "value": _display(spec, getattr(settings, spec.key)),
                "is_set": bool(getattr(settings, spec.key))
                or spec.kind in {"bool", "int", "float"},
                "overridden": row is not None,
                "env_value": _display(spec, _baseline[spec.key]),
                "updated_at": updated.isoformat() if updated else None,
            }
        )
    return out
