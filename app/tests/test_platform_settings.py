"""Platform settings overlay: coercion, masking, and the encryption boundary."""

from __future__ import annotations

import pytest

from callsentry.core.security import DecryptionError, decrypt_secret, encrypt_secret
from callsentry.services import platform_settings as ps


def spec(key: str) -> ps.FieldSpec:
    return ps.BY_KEY[key]


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [
        ("callsentry_local_only", "true", True),
        ("callsentry_local_only", "0", False),
        ("callsentry_local_only", " Off ", False),
        ("max_clarifying_questions", "4", 4),
        ("kb_confidence_threshold", "0.5", 0.5),
        ("ollama_base_url", "http://ollama:11434/", "http://ollama:11434"),
        ("log_level", "debug", "DEBUG"),
        ("claude_model", "  claude-sonnet-5 ", "claude-sonnet-5"),
    ],
)
def test_coerce_accepts_valid_input(key, raw, expected):
    assert ps.coerce(spec(key), raw) == expected


@pytest.mark.parametrize(
    ("key", "raw"),
    [
        ("callsentry_local_only", "maybe"),
        ("max_clarifying_questions", "three"),
        ("max_clarifying_questions", "-1"),
        ("kb_confidence_threshold", "1.5"),
        ("ollama_base_url", "ollama:11434"),
        ("log_level", "VERBOSE"),
        ("twilio_account_sid", "SKnotanaccountsid"),
    ],
)
def test_coerce_rejects_invalid_input(key, raw):
    with pytest.raises(ValueError):
        ps.coerce(spec(key), raw)


def test_serialize_round_trips_through_coerce():
    for key, value in (("callsentry_local_only", True), ("jwt_ttl_seconds", 3600)):
        assert ps.coerce(spec(key), ps.serialize(value)) == value


def test_every_field_has_a_group_label():
    groups = {gid for gid, _ in ps.GROUPS}
    assert {f.group for f in ps.FIELDS} <= groups


def test_boot_only_infrastructure_is_not_exposed():
    keys = {f.key for f in ps.FIELDS}
    boot_only = {"database_url", "redis_url", "encryption_key", "jwt_secret", "internal_api_token"}
    assert not keys & boot_only


def test_platform_secret_cannot_be_read_as_a_tenant_credential(business):
    envelope = encrypt_secret("sk-platform-key", aad="platform")
    assert decrypt_secret(envelope, aad="platform") == "sk-platform-key"
    with pytest.raises(DecryptionError):
        decrypt_secret(envelope, aad=str(business.id))


def test_baseline_reflects_environment():
    # conftest sets CALLSENTRY_LOCAL_ONLY=1, so that is what clearing restores.
    assert ps.baseline("callsentry_local_only") is True
