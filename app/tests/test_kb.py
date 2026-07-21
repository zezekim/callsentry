from __future__ import annotations

import pytest

from callsentry.services.kb import UnsupportedDocument, chunk_text, extract_text


def test_chunk_text_respects_size():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 40 for i in range(20))
    chunks = chunk_text(text, size=500, overlap=50)
    assert chunks
    # Overlap can push a chunk slightly past the target; it must stay bounded.
    assert all(len(c) <= 700 for c in chunks)


def test_chunk_text_splits_oversized_paragraph():
    chunks = chunk_text("x" * 5000, size=900, overlap=100)
    assert len(chunks) > 1
    assert all(len(c) <= 900 for c in chunks)


def test_chunk_text_empty_input():
    assert chunk_text("") == []
    assert chunk_text("   \n\n  ") == []


def test_chunk_text_preserves_content():
    text = "First paragraph here.\n\nSecond paragraph here.\n\nThird paragraph here."
    joined = " ".join(chunk_text(text))
    for marker in ("First", "Second", "Third"):
        assert marker in joined


def test_extract_text_plaintext():
    assert "hello" in extract_text("notes.txt", b"hello world")


def test_extract_text_markdown():
    assert "Hours" in extract_text("faq.md", b"# Hours\n\nNine to five.")


def test_extract_text_rejects_unknown_type():
    with pytest.raises(UnsupportedDocument):
        extract_text("archive.zip", b"PK\x03\x04", "application/zip")


def test_extract_text_survives_bad_encoding():
    """A mis-encoded byte should not blow up an upload."""
    result = extract_text("notes.txt", b"caf\xe9 hours")
    assert "hours" in result
