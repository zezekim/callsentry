"""Structured logging with credential redaction.

Every log line passes through `_redact`, so an API key that leaks into an
exception message or a URL gets masked before it reaches stdout - where it
would otherwise be picked up by whatever ships container logs.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from callsentry.core.security import scrub

_SENSITIVE_KEYS = {
    "api_key", "apikey", "password", "token", "auth_token", "secret",
    "authorization", "encryption_key", "jwt_secret", "access_token",
    "password_hash", "cal_com_api_key", "authorization_token",
}


def _redact(_logger: Any, _method: str, event: dict[str, Any]) -> dict[str, Any]:
    for key, value in list(event.items()):
        if key.lower() in _SENSITIVE_KEYS:
            event[key] = "<redacted>"
        elif isinstance(value, str):
            event[key] = scrub(value)
    return event


def configure(level: str = "INFO") -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level.upper())

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _redact,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )

    # Uvicorn's access log duplicates what we already emit and is noisy.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
