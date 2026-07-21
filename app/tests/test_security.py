from __future__ import annotations

import pytest

from callsentry.core.security import (
    DecryptionError,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    mask,
    scrub,
    verify_password,
)


def test_encrypt_roundtrip():
    envelope = encrypt_secret("cal_live_abc123", aad="biz-1")
    assert envelope != "cal_live_abc123"
    assert decrypt_secret(envelope, aad="biz-1") == "cal_live_abc123"


def test_ciphertext_is_not_reusable_across_tenants():
    """The whole point of binding business id as AAD."""
    envelope = encrypt_secret("secret-value", aad="biz-1")
    with pytest.raises(DecryptionError):
        decrypt_secret(envelope, aad="biz-2")


def test_tampered_ciphertext_is_rejected():
    envelope = encrypt_secret("secret-value", aad="biz-1")
    flipped = envelope[:-4] + ("AAAA" if not envelope.endswith("AAAA") else "BBBB")
    with pytest.raises(DecryptionError):
        decrypt_secret(flipped, aad="biz-1")


def test_nonce_is_not_reused():
    a = encrypt_secret("same-value", aad="biz-1")
    b = encrypt_secret("same-value", aad="biz-1")
    assert a != b, "identical plaintexts must not produce identical ciphertexts"


def test_empty_secret_roundtrips_as_empty():
    assert encrypt_secret("", aad="biz-1") == ""
    assert decrypt_secret("", aad="biz-1") == ""


def test_password_hashing():
    hashed = hash_password("correct-horse-battery")
    assert hashed != "correct-horse-battery"
    assert verify_password("correct-horse-battery", hashed)
    assert not verify_password("wrong", hashed)


def test_long_passphrase_is_supported():
    """Raw bcrypt caps at 72 bytes; we SHA-256 first so length is irrelevant."""
    long_password = "a" * 200
    hashed = hash_password(long_password)
    assert verify_password(long_password, hashed)


def test_long_passphrases_are_not_truncated():
    """Two passphrases sharing a 72-byte prefix must not be interchangeable."""
    base = "x" * 72
    hashed = hash_password(base + "first-suffix")
    assert not verify_password(base + "second-suffix", hashed)


def test_unicode_password():
    password = "pässwörd-日本語-🔑"  # noqa: S105 - test fixture
    assert verify_password(password, hash_password(password))


def test_malformed_hash_fails_closed():
    assert not verify_password("anything", "not-a-bcrypt-hash")
    assert not verify_password("anything", "")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("", "<unset>"), (None, "<unset>"), ("short", "****"), ("sk-abcdefghijkl", "****ijkl")],
)
def test_mask(value, expected):
    assert mask(value) == expected


def test_scrub_removes_keys_from_free_text():
    text = "call failed with key sk-verysecretvalue123 and sid ACdeadbeefdeadbeefdeadbeefdead12"
    cleaned = scrub(text)
    assert "sk-verysecretvalue123" not in cleaned
    assert "ACdeadbeefdeadbeefdeadbeefdead12" not in cleaned
    assert "call failed with key" in cleaned
