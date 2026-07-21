from __future__ import annotations

from datetime import UTC, datetime, timedelta

from callsentry.agents.booking_agent import parse_preferred_time
from callsentry.services.calcom import Slot


def test_parse_empty_defaults_to_tomorrow_morning():
    result = parse_preferred_time("", timezone="America/New_York")
    assert result > datetime.now(UTC)
    assert result < datetime.now(UTC) + timedelta(days=2)


def test_parse_garbage_does_not_raise():
    """A bad STT transcription costs one clarifying turn, not a crash."""
    result = parse_preferred_time("asdkjhasd qwe", timezone="America/New_York")
    assert isinstance(result, datetime)
    assert result.tzinfo is not None


def test_parse_returns_future_time():
    """'Monday at 2' said on Tuesday means next Monday."""
    result = parse_preferred_time("Monday at 2pm", timezone="America/New_York")
    assert result > datetime.now(UTC)


def test_parse_always_returns_timezone_aware():
    for phrase in ("tomorrow at 3", "next Friday morning", "the 25th at noon", ""):
        assert parse_preferred_time(phrase, timezone="UTC").tzinfo is not None


def test_slot_human_renders_in_business_timezone():
    # 2026-07-23 14:30 UTC is 10:30 AM in New York (EDT).
    start = datetime(2026, 7, 23, 14, 30, tzinfo=UTC)
    spoken = Slot(start=start, end=start + timedelta(minutes=30)).human("America/New_York")
    assert "10:30 AM" in spoken
    assert "Thursday" in spoken
