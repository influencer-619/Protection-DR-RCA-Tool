"""Unit tests for consistency checker critical rules."""

from __future__ import annotations

from consistency import ConsistencyEngine
from protection.models import ProtectionAssessment


def _assessment(**kwargs) -> ProtectionAssessment:
    defaults = dict(
        element="51",
        enabled=None,
        pickup=None,
        trip=None,
        expected_operation="UNKNOWN",
        actual_operation="UNKNOWN",
        timing=None,
        consistency="UNVERIFIABLE",
        setting_reference={
            "enabled": {
                "source": "APPROVED_RELAY_BASE",
                "version": "RS-TEST-1",
                "group": "Base",
                "verification_status": "NOT_VERIFIED",
            }
        },
        evidence_ids=["e1"],
        confidence="MEDIUM",
    )
    defaults.update(kwargs)
    return ProtectionAssessment(**defaults)


def test_51_disabled_with_pickup_and_trip_inconsistent():
    a = _assessment(enabled=False, pickup=True, trip=True, actual_operation="OPERATED")
    result = ConsistencyEngine().run(event_id="EVT-1", assessments=[a], timeline=[])
    statuses = {(f.check_type, f.status) for f in result.findings}
    assert ("enabled_vs_pickup", "INCONSISTENT") in statuses
    assert ("enabled_vs_trip", "INCONSISTENT") in statuses
    assert result.has_critical_setting_inconsistency is True
    assert result.rca_must_remain_inconclusive is True
    # Must include investigation hints — not auto relay malfunction
    crit = [
        f
        for f in result.findings
        if f.status == "INCONSISTENT" and f.check_type.startswith("enabled_vs")
    ]
    assert crit
    assert any("malfunction" in f.explanation.lower() for f in crit)
    assert any(f.investigation_hints for f in crit)


def test_enabled_true_pickup_trip_consistent():
    a = _assessment(enabled=True, pickup=True, trip=True, consistency="CONSISTENT")
    result = ConsistencyEngine().run(event_id="EVT-2", assessments=[a])
    ep = next(f for f in result.findings if f.check_type == "enabled_vs_pickup")
    et = next(f for f in result.findings if f.check_type == "enabled_vs_trip")
    assert ep.status == "CONSISTENT"
    assert et.status == "CONSISTENT"
    assert result.rca_must_remain_inconclusive is False


def test_trip_without_pickup_inconsistent():
    a = _assessment(enabled=True, pickup=False, trip=True)
    result = ConsistencyEngine().run(event_id="EVT-3", assessments=[a])
    pt = next(f for f in result.findings if f.check_type == "pickup_vs_trip")
    assert pt.status == "INCONSISTENT"


def test_unverifiable_when_data_missing():
    a = _assessment(enabled=None, pickup=None, trip=None)
    result = ConsistencyEngine().run(event_id="EVT-4", assessments=[a])
    # Empty evidence is skipped — no noise UNVERIFIABLE rows
    assert result.findings == []
    assert result.summary_status == "NOT_AVAILABLE"


def test_overall_consistent_despite_unverifiable_noise_not_emitted():
    a = _assessment(enabled=True, pickup=True, trip=True)
    result = ConsistencyEngine().run(event_id="EVT-5", assessments=[a])
    assert result.summary_status == "CONSISTENT"
