"""SEC-012 — audit payloads must not retain secret-like values."""

from __future__ import annotations

from app.core.secret_redaction import redact_secrets


def test_redacts_nested_password_and_token_keys():
    payload = {
        "username": "eng1",
        "password": "plain-secret",
        "iec61850": {
            "host": "10.0.0.5",
            "mms_password": "ied-pw",
            "port": 102,
        },
        "api_key": "k-123",
        "note": "keep me",
    }
    out = redact_secrets(payload)
    assert out["username"] == "eng1"
    assert out["note"] == "keep me"
    assert out["password"] == "***REDACTED***"
    assert out["api_key"] == "***REDACTED***"
    assert out["iec61850"]["host"] == "10.0.0.5"
    assert out["iec61850"]["mms_password"] == "***REDACTED***"
    assert out["iec61850"]["port"] == 102
    # input not mutated
    assert payload["password"] == "plain-secret"


def test_redacts_hashed_password_key():
    out = redact_secrets({"hashed_password": "$2b$12$abc", "role": "ADMIN"})
    assert out["hashed_password"] == "***REDACTED***"
    assert out["role"] == "ADMIN"


def test_none_and_empty_pass_through():
    assert redact_secrets(None) is None
    assert redact_secrets({"password": None})["password"] is None
    assert redact_secrets({"password": ""})["password"] == ""
