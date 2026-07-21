"""mu-law codec and resampling correctness.

These are verified against Python's stdlib `audioop`, which is the reference
G.711 implementation, so the tables here provably match what Twilio expects.
`audioop` is deprecated (removed in 3.13) - which is exactly why the
production code implements the tables itself - but it is still present in
3.12 and makes an excellent test oracle.
"""

from __future__ import annotations

import numpy as np
import pytest

from agent import audio


def test_mulaw_roundtrip_preserves_signal_shape():
    t = np.linspace(0, 1, 8000, dtype=np.float64)
    original = (np.sin(2 * np.pi * 440 * t) * 16000).astype(np.int16)

    decoded = audio.mulaw_decode(audio.mulaw_encode(original))

    assert decoded.size == original.size
    # mu-law is lossy by design; correlation catches a broken table, which an
    # exact-match assertion could never tolerate.
    correlation = np.corrcoef(original.astype(np.float64), decoded.astype(np.float64))[0, 1]
    assert correlation > 0.99


def test_mulaw_matches_stdlib_reference():
    audioop = pytest.importorskip("audioop", reason="removed in Python 3.13")

    samples = np.array(
        [0, 1, -1, 100, -100, 1000, -1000, 16000, -16000, 32000, -32000], dtype=np.int16
    )
    ours = audio.mulaw_encode(samples)
    reference = audioop.lin2ulaw(samples.tobytes(), 2)

    assert ours == reference, "encoder diverges from the G.711 reference"


def test_mulaw_encode_matches_stdlib_across_full_int16_range():
    """Exhaustive conformance: every representable sample, not just a sample set."""
    audioop = pytest.importorskip("audioop", reason="removed in Python 3.13")

    every_sample = np.arange(-32768, 32768, dtype=np.int16)
    ours = audio.mulaw_encode(every_sample)
    reference = audioop.lin2ulaw(every_sample.tobytes(), 2)

    assert ours == reference


def test_mulaw_decode_matches_stdlib_reference():
    audioop = pytest.importorskip("audioop", reason="removed in Python 3.13")

    encoded = bytes(range(256))
    ours = audio.mulaw_decode(encoded)
    reference = np.frombuffer(audioop.ulaw2lin(encoded, 2), dtype=np.int16)

    np.testing.assert_array_equal(ours, reference)


def test_mulaw_clips_rather_than_wrapping():
    """A too-loud sample must saturate, not wrap around to the opposite sign."""
    loud = np.array([32767, -32768], dtype=np.int16)
    decoded = audio.mulaw_decode(audio.mulaw_encode(loud))
    assert decoded[0] > 20000, "positive peak wrapped or collapsed"
    assert decoded[1] < -20000, "negative peak wrapped or collapsed"


def test_silence_roundtrips_to_silence():
    silence = np.zeros(160, dtype=np.int16)
    decoded = audio.mulaw_decode(audio.mulaw_encode(silence))
    assert audio.rms(decoded) < 10


def test_resample_changes_length_proportionally():
    samples = np.zeros(24000, dtype=np.int16)
    downsampled = audio.resample(samples, source_rate=24000, target_rate=8000)
    assert abs(downsampled.size - 8000) <= 1


def test_resample_is_a_noop_at_matching_rates():
    samples = np.arange(100, dtype=np.int16)
    np.testing.assert_array_equal(
        audio.resample(samples, source_rate=8000, target_rate=8000), samples
    )


def test_resample_preserves_tone_frequency():
    """Downsampling must not shift pitch - a caller would hear it instantly."""
    rate_in, rate_out, freq = 24000, 8000, 440
    t = np.linspace(0, 1, rate_in, endpoint=False)
    tone = (np.sin(2 * np.pi * freq * t) * 16000).astype(np.int16)

    out = audio.resample(tone, source_rate=rate_in, target_rate=rate_out)
    spectrum = np.abs(np.fft.rfft(out.astype(np.float64)))
    peak_hz = np.fft.rfftfreq(out.size, 1 / rate_out)[np.argmax(spectrum)]

    assert abs(peak_hz - freq) < 5


def test_wav_to_mulaw_frames_produces_twilio_sized_frames():
    samples = (np.random.default_rng(0).normal(0, 4000, 24000)).astype(np.int16)
    wav = audio.pcm_to_wav(samples, 24000)

    frames = audio.wav_to_mulaw_frames(wav)

    assert frames
    # Every frame but the last must be exactly 20 ms of 8 kHz mu-law.
    assert all(len(f) == audio.TWILIO_FRAME_SAMPLES for f in frames[:-1])
    assert len(frames[-1]) <= audio.TWILIO_FRAME_SAMPLES
    # 1 second in should yield ~50 frames of 20 ms out.
    assert 48 <= len(frames) <= 52


def test_wav_to_mulaw_frames_downmixes_stereo():
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(8000)
        out.writeframes(np.zeros(1600, dtype=np.int16).tobytes())

    frames = audio.wav_to_mulaw_frames(buffer.getvalue())
    assert frames, "stereo input should still produce mono frames"


def test_wav_to_mulaw_frames_rejects_non_16bit():
    import io
    import wave

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(1)
        out.setframerate(8000)
        out.writeframes(b"\x00" * 800)

    with pytest.raises(ValueError, match="16-bit"):
        audio.wav_to_mulaw_frames(buffer.getvalue())


def test_pcm_to_wav_roundtrip():
    import io
    import wave

    samples = np.arange(-1000, 1000, dtype=np.int16)
    wav = audio.pcm_to_wav(samples, 8000)

    with wave.open(io.BytesIO(wav), "rb") as source:
        assert source.getframerate() == 8000
        assert source.getnchannels() == 1
        assert source.getsampwidth() == 2
        decoded = np.frombuffer(source.readframes(source.getnframes()), dtype=np.int16)

    np.testing.assert_array_equal(decoded, samples)


def test_rms_of_empty_is_zero():
    assert audio.rms(np.zeros(0, dtype=np.int16)) == 0.0
