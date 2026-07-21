"""Cal.com integration: availability, booking, cancellation.

Point CALCOM_BASE_URL at a self-hosted Cal.com to keep this tier local and
free; the hosted API works identically. Per-business API keys override the
platform-wide one and are stored AES-256-GCM encrypted.

Double-booking is prevented on two levels: Cal.com itself rejects a slot it
has already issued, and `find_slot` only ever offers times returned by the
live availability call.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import structlog

from callsentry.config import get_settings

log = structlog.get_logger(__name__)


@dataclass
class Slot:
    start: datetime
    end: datetime

    def human(self, tz: str) -> str:
        from zoneinfo import ZoneInfo

        local = self.start.astimezone(ZoneInfo(tz))
        return local.strftime("%A %B %-d at %-I:%M %p")


@dataclass
class BookingResult:
    ok: bool
    event_id: str | None = None
    start: datetime | None = None
    error: str | None = None


class CalComError(RuntimeError):
    pass


class CalComService:
    def __init__(self, api_key: str | None = None, event_type_id: str | None = None) -> None:
        settings = get_settings()
        self.base_url = settings.calcom_base_url.rstrip("/")
        self.api_key = api_key or settings.calcom_api_key
        self.event_type_id = event_type_id

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.event_type_id)

    async def _request(self, method: str, path: str, **kwargs: object) -> dict:
        params = dict(kwargs.pop("params", {}) or {})  # type: ignore[arg-type]
        params["apiKey"] = self.api_key
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.request(
                method, f"{self.base_url}{path}", params=params, **kwargs  # type: ignore[arg-type]
            )
        if resp.status_code >= 400:
            raise CalComError(f"cal.com {method} {path} -> {resp.status_code}: {resp.text[:200]}")
        return resp.json() if resp.content else {}

    async def available_slots(
        self, *, start: datetime, end: datetime, timezone: str = "UTC"
    ) -> list[Slot]:
        if not self.configured:
            raise CalComError("cal.com is not configured for this business")

        data = await self._request(
            "GET",
            "/slots",
            params={
                "eventTypeId": self.event_type_id,
                "startTime": start.astimezone(UTC).isoformat(),
                "endTime": end.astimezone(UTC).isoformat(),
                "timeZone": timezone,
            },
        )

        slots: list[Slot] = []
        # Response shape: {"slots": {"2026-07-23": [{"time": "..."}, ...]}}
        for _day, entries in (data.get("slots") or {}).items():
            for entry in entries:
                raw = entry.get("time") or entry.get("start")
                if not raw:
                    continue
                begin = datetime.fromisoformat(raw.replace("Z", "+00:00"))
                slots.append(Slot(start=begin, end=begin + timedelta(minutes=30)))
        return sorted(slots, key=lambda s: s.start)

    async def find_slot(
        self, *, preferred: datetime, timezone: str = "UTC", window_days: int = 14
    ) -> Slot | None:
        """Nearest real opening to what the caller asked for.

        Never invents a time - only returns something Cal.com just said was
        free, which is what keeps the agent from promising a booked slot.
        """
        window_start = max(preferred - timedelta(hours=12), datetime.now(UTC))
        window_end = preferred + timedelta(days=window_days)
        slots = await self.available_slots(start=window_start, end=window_end, timezone=timezone)
        if not slots:
            return None
        return min(slots, key=lambda s: abs((s.start - preferred).total_seconds()))

    async def book(
        self,
        *,
        start: datetime,
        name: str,
        email: str,
        phone: str | None = None,
        reason: str | None = None,
        timezone: str = "UTC",
    ) -> BookingResult:
        try:
            data = await self._request(
                "POST",
                "/bookings",
                json={
                    "eventTypeId": int(self.event_type_id or 0),
                    "start": start.astimezone(UTC).isoformat(),
                    "responses": {
                        "name": name,
                        "email": email,
                        "phone": phone or "",
                        "notes": reason or "Booked by CallSentry AI receptionist",
                    },
                    "timeZone": timezone,
                    "language": "en",
                    "metadata": {"source": "callsentry"},
                },
            )
        except CalComError as exc:
            log.warning("calcom.book_failed", error=str(exc))
            return BookingResult(ok=False, error=str(exc))

        booking = data.get("booking") or data
        event_id = str(booking.get("uid") or booking.get("id"))
        return BookingResult(ok=True, event_id=event_id, start=start)

    async def cancel(self, event_id: str, *, reason: str = "Cancelled by caller") -> bool:
        try:
            await self._request(
                "DELETE", f"/bookings/{event_id}", params={"cancellationReason": reason}
            )
            return True
        except CalComError as exc:
            log.warning("calcom.cancel_failed", event_id=event_id, error=str(exc))
            return False
