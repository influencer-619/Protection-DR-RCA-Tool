"""Acceptance-oriented policy tests (empty dashboard shape, 51, distance)."""

from __future__ import annotations

from consistency import ConsistencyEngine
from fault_analysis import classify_fault
from protection.models import ProtectionAssessment
from rca import HypothesisEngine


def test_empty_dashboard_stats_shape():
    """DashboardStats defaults must be zeros — no fabricated events."""
    from app.schemas.rules import DashboardStats

    s = DashboardStats()
    assert s.total_events == 0
    assert s.awaiting_analysis == 0
    assert s.awaiting_review == 0
    assert s.completed_reports == 0
    assert s.consistency_issues == 0
    assert s.high_severity_findings == 0
    assert s.rca_inconclusive == 0
    assert s.parser_dq_issues == 0
    assert s.trend_30d == []
    assert s.attention == []
    assert s.recent_events == []


def test_51_case_no_relay_malfunction_confirmed():
    from consistency.engine import ConsistencyResult
    from fault_analysis import FaultClassificationResult

    a = ProtectionAssessment(
        element="51",
        enabled=False,
        pickup=True,
        trip=True,
        expected_operation="NOT_OPERATE",
        actual_operation="OPERATED",
        timing=None,
        consistency="INCONSISTENT",
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
    cons = ConsistencyEngine().run(event_id="EVT-51", assessments=[a], timeline=[])
    assert cons.has_critical_setting_inconsistency is True
    assert any(f.status == "INCONSISTENT" for f in cons.findings)

    # Prefer engine flag when present; also force inconclusive path like production
    cons_forced = ConsistencyResult(
        findings=cons.findings,
        has_critical_setting_inconsistency=True,
        rca_must_remain_inconclusive=True,
        summary_status="INCONSISTENT",
    )
    fault = FaultClassificationResult(
        fault_type="UNKNOWN", status="UNKNOWN", confidence="LOW"
    )
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=[a],
        consistency=cons_forced,
        electrical_flags={},
    )
    assert rca.forced_inconclusive is True
    for h in rca.hypotheses:
        if h.hypothesis_id == "RELAY_MISOPERATION":
            assert h.status != "CONFIRMED"


def test_fault_distance_not_invented_without_inputs():
    from electrical_analysis.analyzer import ElectricalAnalysisResult

    elec = ElectricalAnalysisResult(
        record_id="EVT-Z",
        nominal_frequency_hz=50.0,
        sample_rate_hz=None,
        limitations=["insufficient inputs"],
    )
    result = classify_fault(elec, line_params=None)
    dist = result.distance or {}
    assert dist.get("status") == "NOT_CALCULABLE"
    assert dist.get("value_km") is None
    assert result.fault_type in ("UNKNOWN", "INCONCLUSIVE") or result.status in (
        "UNKNOWN",
        "INCONCLUSIVE",
        "DATA_INSUFFICIENT",
    )
