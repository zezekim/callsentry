"""Audio codecs for Twilio Media Streams.

Twilio speaks 8 kHz mono G.711 mu-law, base64-encoded inside JSON frames.
Kokoro emits 24 kHz PCM. Everything here converts between the two.

mu-law is implemented with numpy lookup tables rather than the stdlib
`audioop` module, which is deprecated in 3.11 and removed in 3.13.
"""

from __future__ import annotations

import io
import wave

import numpy as np

TWILIO_SAMPLE_RATE = 8_000
TWILIO_FRAME_SAMPLES = 160  # 20 ms at 8 kHz - Twilio's frame size

# G.711 encodes 14-bit magnitudes, so 16-bit input is shifted down by 2 first.
_BIAS_14 = 0x84 >> 2  # 33
_CLIP_14 = 8159
# Upper bound of each of the 8 companding segments. The segment index is the
# position of the first bound that the biased magnitude fits inside.
_SEG_UEND = np.array(
    [0x3F, 0x7F, 0xFF, 0x1FF, 0x3FF, 0x7FF, 0xFFF, 0x1FFF], dtype=np.int32
)


def _build_mulaw_decode_table() -> np.ndarray:
    """mu-law byte -> int16 sample. 256 entries, computed once at import."""
    table = np.zeros(256, dtype=np.int16)
    for byte in range(256):
        value = ~byte & 0xFF
        sign = value & 0x80
        exponent = (value >> 4) & 0x07
        mantissa = value & 0x0F
        # Reconstruct the 14-bit magnitude, then scale back up to 16-bit.
        sample = (((mantissa << 3) + 0x84) << exponent) - 0x84
        table[byte] = -sample if sign else sample
    return table


_DECODE_TABLE = _build_mulaw_decode_table()


def mulaw_decode(payload: bytes) -> np.ndarray:
    """mu-law bytes -> int16 PCM samples."""
    return _DECODE_TABLE[np.frombuffer(payload, dtype=np.uint8)]


def mulaw_encode(samples: np.ndarray) -> bytes:
    """int16 PCM samples -> mu-law bytes.

    Implements the reference G.711 companding curve (the same one CPython's
    `audioop.lin2ulaw` uses), so output is bit-identical to what Twilio's
    decoder expects. Note the sign is applied as an XOR mask rather than a
    bit, which is what keeps 0x7F ("negative zero") out of the output.
    """
    pcm = np.asarray(samples, dtype=np.int32) >> 2  # 16-bit -> 14-bit
    mask = np.where(pcm < 0, 0x7F, 0xFF).astype(np.int32)

    magnitude = np.minimum(np.abs(pcm), _CLIP_14) + _BIAS_14
    segment = np.searchsorted(_SEG_UEND, magnitude, side="left").astype(np.int32)

    # Saturated samples fall past the last segment and encode to the extreme.
    saturated = segment >= len(_SEG_UEND)
    safe_segment = np.where(saturated, 0, segment)
    mantissa = (magnitude >> (safe_segment + 1)) & 0x0F

    uval = np.where(saturated, 0x7F, (safe_segment << 4) | mantissa)
    return (uval ^ mask).astype(np.uint8).tobytes()


def resample(samples: np.ndarray, *, source_rate: int, target_rate: int) -> np.ndarray:
    """Linear-interpolation resample.

    Adequate for 8 kHz telephony: the channel is band-limited to ~3.4 kHz
    anyway, so a higher-order filter buys nothing a caller can hear.
    """
    if source_rate == target_rate or samples.size == 0:
        return samples

    duration = samples.size / source_rate
    target_count = int(duration * target_rate)
    if target_count <= 0:
        return np.zeros(0, dtype=samples.dtype)

    source_positions = np.arange(samples.size, dtype=np.float64)
    target_positions = np.linspace(0, samples.size - 1, target_count)
    return np.interp(target_positions, source_positions, samples).astype(samples.dtype)


def wav_to_mulaw_frames(wav_bytes: bytes) -> list[bytes]:
    """Decode a WAV blob and re-encode it as 20 ms Twilio mu-law frames."""
    with wave.open(io.BytesIO(wav_bytes), "rb") as source:
        rate = source.getframerate()
        channels = source.getnchannels()
        width = source.getsampwidth()
        raw = source.readframes(source.getnframes())

    if width != 2:
        raise ValueError(f"expected 16-bit PCM, got {width * 8}-bit")

    samples = np.frombuffer(raw, dtype=np.int16)
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)

    samples = resample(samples, source_rate=rate, target_rate=TWILIO_SAMPLE_RATE)
    encoded = mulaw_encode(samples)

    return [
        encoded[i : i + TWILIO_FRAME_SAMPLES]
        for i in range(0, len(encoded), TWILIO_FRAME_SAMPLES)
    ]


def pcm_to_wav(samples: np.ndarray, sample_rate: int) -> bytes:
    """int16 samples -> a WAV file the worker's STT endpoint accepts."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(sample_rate)
        out.writeframes(np.asarray(samples, dtype=np.int16).tobytes())
    return buffer.getvalue()


def rms(samples: np.ndarray) -> float:
    """Root-mean-square level, used by the endpointer."""
    if samples.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples.astype(np.float64)))))
