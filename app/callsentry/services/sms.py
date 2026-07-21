"""Outbound SMS via Twilio: booking confirmations and 24h reminders.

Twilio is the one component with no local substitute, so there is no local
tier here - just Twilio or a no-op that logs. A failed SMS never raises into
the caller's flow; the appointment still exists either way.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import structlog

from callsentry.config import get_settings
from callsentry.core.security import mask

log = structlog.get_logger(__name__)

SMS_SEGMENT_COST_USD = 0.0079


@dataclass
class SMSResult:
    sent: bool
    provider: str
    message_sid: str | None = None
    segments: int = 1
    cost_usd: float = 0.0
    error: str | None = None


class SMSService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None

    def _twilio(self):  # type: ignore[no-untyped-def]
        if self._client is None:
            from twilio.rest import Client

            self._client = Client(
                self.settings.twilio_account_sid, self.settings.twilio_auth_token
            )
        return self._client

    async def send(self, *, to: str, body: str, from_: str | None = None) -> SMSResult:
        sender = from_ or self.settings.twilio_phone_number
        segments = max(1, (len(body) + 152) // 153)

        if not (self.settings.twilio_account_sid and self.settings.twilio_auth_token and sender):
            log.info("sms.skipped_not_configured", to=mask(to), chars=len(body))
            return SMSResult(sent=False, provider="mock-telephony", error="twilio not configured")

        try:
            # The Twilio SDK is synchronous; keep it off the event loop.
            message = await asyncio.to_thread(
                lambda: self._twilio().messages.create(to=to, from_=sender, body=body)
            )
        except Exception as exc:  # noqa: BLE001 - never break the caller's flow
            log.warning("sms.failed", to=mask(to), error=str(exc))
            return SMSResult(sent=False, provider="twilio", error=str(exc))

        log.info("sms.sent", to=mask(to), sid=message.sid, segments=segments)
        return SMSResult(
            sent=True,
            provider="twilio",
            message_sid=message.sid,
            segments=segments,
            cost_usd=round(segments * SMS_SEGMENT_COST_USD, 6),
        )


_service: SMSService | None = None


def get_sms() -> SMSService:
    global _service
    if _service is None:
        _service = SMSService()
    return _service
