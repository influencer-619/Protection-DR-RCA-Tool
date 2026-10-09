"""Stage E — Incident correlation rules (no timestamp-only merge)."""

from __future__ import annotations

import pytest

from app.services.incident_service import (
    ALLOWED_REASONS,
    FORBIDDEN_AUTO_REASONS,
    normalize_reason,
    validate_correlation_reason,
    validate_member_role,
)


def test_forbidden_timestamp_only_reasons():
    for bad in (
        "TIMESTAMP_ONLY",
        "TIMESTAMP_WINDOW",
        "AUTO_TIME_CORRELATE",
        "TIME_PROXIMITY",
        "AUTO_MERGE",
    ):
        assert bad in FORBIDDEN_AUTO_REASONS
        with pytest.raises(ValueError, match="not allowed|timestamp"):
            validate_correlation_reason(bad)


def test_missing_reason_rejected():
    with pytest.raises(ValueError, match="required"):
        validate_correlation_reason("")
    with pytest.raises(ValueError, match="required"):
        validate_correlation_reason(None)


def test_allowed_explicit_reasons():
    for ok in ALLOWED_REASONS:
        assert validate_correlation_reason(ok) == ok
    assert validate_correlation_reason("engineer_link") == "ENGINEER_LINK"
    assert validate_correlation_reason("late-dr-attach") == "LATE_DR_ATTACH"


def test_unknown_reason_rejected():
    with pytest.raises(ValueError, match="unknown"):
        validate_correlation_reason("GUESS_SAME_FAULT")


def test_member_roles():
    assert validate_member_role("INITIATOR") == "INITIATOR"
    assert validate_member_role(None) == "SOURCE"
    with pytest.raises(ValueError):
        validate_member_role("RANDOM")


def test_normalize_reason():
    assert normalize_reason("  late dr attach ") == "LATE_DR_ATTACH"
