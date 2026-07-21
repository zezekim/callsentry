"""Endpointing behaviour - when the agent decides the caller has finished."""

from __future__ import annotations

import numpy as np

from agent.pipeline import (
    MAX_UTTERANCE_FRAMES,
    MIN_SPEECH_FRAMES,
    SILENCE_FRAMES_TO_ENDPOINT,
    SPEECH_RMS_THRESHOLD,
    CallContext,
    Endpointer,
)

FRAME = 160


def _speech(level: float = SPEECH_RMS_THRESHOLD * 3) -> np.ndarray:
    rng = np.random.default_rng(1)
    return (rng.normal(0, level, FRAME)).astype(np.int16)


def _silence() -> np.ndarray:
    return np.zeros(FRAME, dtype=np.int16)


def test_silence_alone_never_endpoints():
    ep = Endpointer()
    for _ in range(500):
        assert not ep.push(_silence())


def test_speech_then_silence_endpoints():
    ep = Endpointer()
    for _ in range(MIN_SPEECH_FRAMES + 5):
        assert not ep.push(_speech())

    fired = False
    for _ in range(SILENCE_FRAMES_TO_ENDPOINT + 2):
        if ep.push(_silence()):
            fired = True
            break
    assert fired


def test_brief_noise_does_not_endpoint():
    """A cough or line click should not be sent off for transcription."""
    ep = Endpointer()
    for _ in range(MIN_SPEECH_FRAMES - 3):
        ep.push(_speech())
    for _ in range(SILENCE_FRAMES_TO_ENDPOINT + 10):
        assert not ep.push(_silence())


def test_pause_mid_sentence_does_not_endpoint_early():
    """A short breath between words must not cut the caller off."""
    ep = Endpointer()
    for _ in range(MIN_SPEECH_FRAMES + 2):
        ep.push(_speech())
    for _ in range(SILENCE_FRAMES_TO_ENDPOINT // 2):
        assert not ep.push(_silence())
    for _ in range(5):
        assert not ep.push(_speech())


def test_hard_cap_endpoints_a_rambling_turn():
    ep = Endpointer()
    fired = any(ep.push(_speech()) for _ in range(MAX_UTTERANCE_FRAMES + 10))
    assert fired, "an unbounded utterance would hang the call"


def test_take_returns_audio_and_resets():
    ep = Endpointer()
    for _ in range(MIN_SPEECH_FRAMES + 2):
        ep.push(_speech())

    samples = ep.take()
    assert samples.size > 0
    assert ep.buffer == []
    assert ep.speech_frames == 0
    assert not ep.triggered


def test_leading_silence_is_not_buffered():
    """Line noise before speech shouldn't be sent to the transcriber."""
    ep = Endpointer()
    for _ in range(50):
        ep.push(_silence())
    assert ep.buffer == []

    ep.push(_speech())
    assert len(ep.buffer) == 1


def test_transcript_accumulates_in_order():
    ctx = CallContext(call_id="abc")
    ctx.log_line("Assistant", "Thanks for calling.")
    ctx.log_line("Caller", "I'd like an appointment.")
    ctx.log_line("Caller", "   ")  # blank lines are dropped

    assert ctx.full_transcript == (
        "Assistant: Thanks for calling.\nCaller: I'd like an appointment."
    )
