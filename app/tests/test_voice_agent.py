"""Business-hours logic, compliance disclosures, and conversation guards."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from callsentry.agents.voice_agent import (
    CallState,
    _is_affirmative,
    is_open,
    opening_line,
    spoken_hours,
)


def _at(business, *, day: int, hour: int, minute: int = 0) -> datetime:
    """A datetime in the business's own timezone. 2026-07-20 is a Monday."""
    return datetime(2026, 7, 20 + day, hour, minute, tzinfo=ZoneInfo(business.timezone))


@pytest.mark.parametrize(
    ("day", "hour", "expected"),
    [
        (0, 12, True),   # Monday midday
        (0, 9, True),    # exactly opening time
        (0, 8, False),   # before opening
        (0, 17, False),  # exactly closing time is closed
        (0, 18, False),  # after closing
        (4, 16, True),   # Friday afternoon
        (5, 12, False),  # Saturday - configured closed
        (6, 12, False),  # Sunday - configured closed
    ],
)
def test_is_open(business, day, hour, expected):
    assert is_open(business, at=_at(business, day=day, hour=hour)) is expected


def test_is_open_fails_open_on_malformed_hours(business):
    """A config typo should not silently make a business unreachable."""
    business.business_hours = {"mon": ["nine", "five"]}
    assert is_open(business, at=_at(business, day=0, hour=12)) is True


def test_opening_line_discloses_ai_and_recording(business):
    line = opening_line(business, after_hours=False)
    assert "AI assistant" in line
    assert "recorded" in line
    assert business.name in line


def test_after_hours_opening_states_hours(business):
    line = opening_line(business, after_hours=True)
    assert "AI assistant" in line
    assert "closed" in line.lower()
    assert "Monday through Friday" in line


def test_greeting_override_is_respected(business):
    business.greeting_override = "Custom greeting - AI assistant, recorded line."
    assert opening_line(business, after_hours=False) == business.greeting_override


def test_spoken_hours_handles_appointment_only(business):
    business.business_hours = {d: None for d in ("mon", "tue", "wed", "thu", "fri", "sat", "sun")}
    assert spoken_hours(business) == "by appointment only"


@pytest.mark.parametrize(
    "text", ["yes", "Yeah", "that works", "sounds good", "Sure.", "book it", "perfect!"]
)
def test_affirmative_detection(text):
    assert _is_affirmative(text)


@pytest.mark.parametrize("text", ["no", "not really", "what else do you have", "hmm"])
def test_non_affirmative_detection(text):
    assert not _is_affirmative(text)


def test_history_is_bounded(business):
    """Long calls must not grow the prompt without limit."""
    state = CallState(call_id="c", business_id=str(business.id), caller_number="+1555")
    for i in range(200):
        state.remember("user", f"turn {i}")
        state.remember("assistant", f"reply {i}")
    assert len(state.history) <= 24


def test_merge_entities_does_not_overwrite_known_values():
    state = CallState(call_id="c", business_id="b", caller_number="+1555")
    state.merge_entities({"name": "Alice", "email": ""})
    state.merge_entities({"name": "", "email": "alice@example.com"})
    # A later blank must not erase a name we already captured.
    assert state.collected == {"name": "Alice", "email": "alice@example.com"}
