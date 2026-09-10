"""Unit tests for RCA hypothesis engine."""

from __future__ import annotations

from consistency.engine import ConsistencyResult
from consistency.findings import ConsistencyFinding
from fault_analysis import FaultClassificationResult
from protection.models import ProtectionAssessment
from rca import HypothesisEngine
from settings.hierarchy.resolver import (
    SettingRecord,
    SettingSource,
    resolve_setting,
)


def test_setting_resolution_never_silent():
    candidates = [
        SettingRecord(
            setting_id="s1",
            relay_id="r1",
            setting_group="Base",
            parameter="enabled",
            value=False,
            enabled=False,
            version="RS-1",
            source=SettingSource.APPROVED_RELAY_BASE,
            approval_status="APPROVED",
            verified=True,
            element="51",
        )
    ]
    res = resolve_setting("enabled", candidates, element="51")
    assert res.source == SettingSource.APPROVED_RELAY_BASE.value
    assert res.version == "RS-1"
    assert res.group == "Base"
    assert res.verification_status in ("VERIFIED", "NOT_VERIFIED")
    assert res.explanation


def test_rca_inconclusive_on_critical_consistency():
    fault = FaultClassificationResult(
        fault_type="AG", status="CLASSIFIED", confidence="MEDIUM"
    )
    assessments = [
        ProtectionAssessment(
            element="51",
            enabled=False,
            pickup=True,
            trip=True,
            expected_operation="NOT_OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="INCONSISTENT",
            setting_reference={},
            evidence_ids=[],
            confidence="LOW",
        )
    ]
    cons = ConsistencyResult(
        findings=[],
        has_critical_setting_inconsistency=True,
        rca_must_remain_inconclusive=True,
        summary_status="INCONSISTENT",
    )
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=cons,
        electrical_flags={"current_increase": True},
    )
    assert rca.forced_inconclusive is True
    assert rca.primary is not None
    assert rca.primary.status == "INCONCLUSIVE"
    # Must not confirm relay misoperation
    mis = next(h for h in rca.hypotheses if h.hypothesis_id == "RELAY_MISOPERATION")
    assert mis.status != "CONFIRMED"


def test_never_confirmed_without_evidence():
    fault = FaultClassificationResult(
        fault_type="UNKNOWN", status="UNKNOWN", confidence="INCONCLUSIVE"
    )
    cons = ConsistencyResult(summary_status="UNVERIFIABLE")
    rca = HypothesisEngine().run(
        fault=fault, assessments=[], consistency=cons, electrical_flags={}
    )
    confirmed = [h for h in rca.hypotheses if h.status == "CONFIRMED"]
    assert confirmed == []


def test_rca_ranks_fault_from_available_data():
    """AG + CONSISTENT 51 → feeder/local primary (not distance catch-all)."""
    fault = FaultClassificationResult(
        fault_type="AG",
        status="CLASSIFIED",
        confidence="MEDIUM",
        evidence={"available": True, "Ia_elevated": True, "ground": True},
    )
    assessments = [
        ProtectionAssessment(
            element="51",
            enabled=True,
            pickup=True,
            trip=False,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["pu"],
            confidence="MEDIUM",
        )
    ]
    cons = ConsistencyResult(summary_status="CONSISTENT")
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=cons,
        electrical_flags={},
    )
    assert rca.forced_inconclusive is False
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "INTERNAL_FEEDER_FAULT"
    assert rca.primary.status in ("PROBABLE", "POSSIBLE", "CONFIRMED")
    assert rca.primary.supporting_evidence
    assert "COMTRADE" in rca.primary.statement or "fault" in rca.primary.statement.lower()
    line = next(h for h in rca.hypotheses if h.hypothesis_id == "EXTERNAL_LINE_FAULT")
    assert line.score < rca.primary.score


def test_rca_distance_scheme_prefers_line_fault():
    """Operated 21 + classified fault → EXTERNAL_LINE_FAULT over feeder."""
    fault = FaultClassificationResult(
        fault_type="AG",
        status="CLASSIFIED",
        confidence="HIGH",
        evidence={"available": True, "Ia_elevated": True, "ground": True},
        distance={"distance_km": 12.4, "status": "OK"},
    )
    assessments = [
        ProtectionAssessment(
            element="21",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["e"],
            confidence="MEDIUM",
        )
    ]
    cons = ConsistencyResult(summary_status="CONSISTENT")
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=cons,
        electrical_flags={"current_increase": True},
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "EXTERNAL_LINE_FAULT"
    feeder = next(h for h in rca.hypotheses if h.hypothesis_id == "INTERNAL_FEEDER_FAULT")
    assert rca.primary.score > feeder.score


def test_rca_differential_prefers_transformer():
    fault = FaultClassificationResult(
        fault_type="ABC", status="CLASSIFIED", confidence="MEDIUM"
    )
    assessments = [
        ProtectionAssessment(
            element="87T",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["d"],
            confidence="MEDIUM",
        )
    ]
    cons = ConsistencyResult(summary_status="CONSISTENT")
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=cons,
        electrical_flags={"current_increase": True},
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "TRANSFORMER_INTERNAL_FAULT"


def test_rca_bus_diff_prefers_bus_zone():
    fault = FaultClassificationResult(
        fault_type="AB", status="CLASSIFIED", confidence="MEDIUM"
    )
    assessments = [
        ProtectionAssessment(
            element="87B",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["b"],
            confidence="MEDIUM",
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={"current_increase": True},
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "BUS_ZONE_FAULT"


def test_rca_earth_fault_leans_feeder():
    fault = FaultClassificationResult(
        fault_type="AG",
        status="CLASSIFIED",
        confidence="MEDIUM",
        evidence={"ground": True, "available": True, "Ia_elevated": True},
    )
    assessments = [
        ProtectionAssessment(
            element="51N",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["ef"],
            confidence="MEDIUM",
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={"current_increase": True},
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "INTERNAL_FEEDER_FAULT"
    assert "earth" in rca.primary.statement.lower() or "51N" in rca.primary.statement


def test_rca_breaker_failure_scheme():
    fault = FaultClassificationResult(
        fault_type="AG", status="PROBABLE", confidence="LOW"
    )
    assessments = [
        ProtectionAssessment(
            element="50BF",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["bf"],
            confidence="MEDIUM",
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={"current_persists": True, "trip_command": True},
    )
    bf = next(h for h in rca.hypotheses if h.hypothesis_id == "BREAKER_FAILURE")
    assert bf.score >= 0.5
    assert bf.status in ("PROBABLE", "POSSIBLE", "CONFIRMED")


def test_rca_probable_without_all_confirmed_requirements():
    fault = FaultClassificationResult(
        fault_type="AG", status="CLASSIFIED", confidence="HIGH"
    )
    cons = ConsistencyResult(summary_status="CONSISTENT")
    assessments = [
        ProtectionAssessment(
            element="21",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["e"],
            confidence="MEDIUM",
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=cons,
        electrical_flags={"current_increase": True},
    )
    primary = rca.primary
    assert primary is not None
    assert primary.status in ("PROBABLE", "CONFIRMED")
    assert primary.hypothesis_id == "EXTERNAL_LINE_FAULT"


def test_ml_does_not_override_deterministic():
    fault = FaultClassificationResult(
        fault_type="AG", status="CLASSIFIED", confidence="MEDIUM"
    )
    cons = ConsistencyResult(summary_status="CONSISTENT")
    assessments = [
        ProtectionAssessment(
            element="21",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["e"],
            confidence="MEDIUM",
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=cons,
        electrical_flags={"current_increase": True},
        ml_available=True,
        ml_supports={"RELAY_MISOPERATION": 1.0, "EXTERNAL_LINE_FAULT": 0.0},
    )
    # Even with ML pushing misoperation, primary should not be CONFIRMED misoperation
    # without deterministic support
    mis = next(h for h in rca.hypotheses if h.hypothesis_id == "RELAY_MISOPERATION")
    assert mis.status != "CONFIRMED"


def test_rca_xfmr_diff_rejects_line_causes():
    """87T trip → transformer primary; vegetation/lightning/cable/bus are UNLIKELY."""
    fault = FaultClassificationResult(
        fault_type="ABC", status="CLASSIFIED", confidence="MEDIUM"
    )
    assessments = [
        ProtectionAssessment(
            element="87T",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["d"],
            confidence="MEDIUM",
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={"current_increase": True},
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "TRANSFORMER_INTERNAL_FAULT"
    by_id = {h.hypothesis_id: h for h in rca.hypotheses}
    for hid in (
        "VEGETATION",
        "LIGHTNING",
        "CABLE_FAULT",
        "INSULATION_FLASHOVER",
        "BUS_ZONE_FAULT",
        "GENERATOR_INTERNAL_FAULT",
        "EXTERNAL_LINE_FAULT",
        "INTERNAL_FEEDER_FAULT",
    ):
        assert by_id[hid].status == "UNLIKELY", hid
    # CT sat remains a competing instrumentation hyp without waveform proof
    assert by_id["CT_SATURATION"].status in ("INCONCLUSIVE", "UNLIKELY", "POSSIBLE")


def test_rca_line_causes_need_field_evidence():
    """21 + classified fault → line primary; lightning/vegetation stay INCONCLUSIVE without evidence."""
    fault = FaultClassificationResult(
        fault_type="AG",
        status="CLASSIFIED",
        confidence="HIGH",
        evidence={"available": True, "Ia_elevated": True, "ground": True},
    )
    assessments = [
        ProtectionAssessment(
            element="21",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["e"],
            confidence="MEDIUM",
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={"current_increase": True},
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "EXTERNAL_LINE_FAULT"
    by_id = {h.hypothesis_id: h for h in rca.hypotheses}
    assert by_id["LIGHTNING"].status == "INCONCLUSIVE"
    assert by_id["VEGETATION"].status == "INCONCLUSIVE"
    assert by_id["CABLE_FAULT"].status == "INCONCLUSIVE"
    assert by_id["BUS_ZONE_FAULT"].status == "UNLIKELY"
    assert by_id["TRANSFORMER_INTERNAL_FAULT"].status == "UNLIKELY"


def test_rca_xfmr_through_fault_excluded_confirms():
    """87T + Id/Ir above characteristic → through_fault_excluded → CONFIRMED."""
    fault = FaultClassificationResult(
        fault_type="ABC", status="CLASSIFIED", confidence="HIGH"
    )
    # Internal: I1 ≈ 10∠0, I2 ≈ 0 → high Id, moderate Ir
    assessments = [
        ProtectionAssessment(
            element="87T",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["d"],
            confidence="MEDIUM",
            metadata={
                "differential": {
                    "status": "OK",
                    "operate_a": 10.0,
                    "restraint_a": 5.0,
                    "threshold_a": 1.7,  # 0.2 + 0.3*5
                    "pickup_a": 0.2,
                    "slope": 0.3,
                    "operate_expected": True,
                },
                "inrush": {"status": "UNLIKELY"},
            },
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={"current_increase": True},
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "TRANSFORMER_INTERNAL_FAULT"
    assert rca.primary.status == "CONFIRMED"
    assert "through_fault_excluded" not in rca.primary.missing_evidence
    assert "through_fault_excluded" in (
        rca.primary.supporting_evidence or []
    ) or "differential_operated" in (rca.primary.supporting_evidence or [])


def test_rca_xfmr_through_fault_not_excluded_without_idir():
    """87T operate alone without Id/Ir — soft exclusion when no CT-sat/inrush → CONFIRMED."""
    fault = FaultClassificationResult(
        fault_type="ABC", status="CLASSIFIED", confidence="MEDIUM"
    )
    assessments = [
        ProtectionAssessment(
            element="87T",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["d"],
            confidence="MEDIUM",
            metadata={
                "differential": {
                    "status": "NOT_CALCULABLE",
                    "operate_expected": None,
                },
                "inrush": {"status": "NOT_INDICATED"},
            },
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "current_increase": True,
            "detectors": {"ct_saturation": {"status": "NOT_INDICATED", "suspects": []}},
        },
    )
    xfmr = next(h for h in rca.hypotheses if h.hypothesis_id == "TRANSFORMER_INTERNAL_FAULT")
    assert xfmr.status == "CONFIRMED"
    assert "through_fault_excluded" not in xfmr.missing_evidence


def test_rca_xfmr_through_fault_blocked_by_phase_ct_sat():
    """Soft through-fault exclusion blocked when phase CT-sat is POSSIBLE."""
    fault = FaultClassificationResult(
        fault_type="ABC", status="CLASSIFIED", confidence="MEDIUM"
    )
    assessments = [
        ProtectionAssessment(
            element="87T",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["d"],
            confidence="MEDIUM",
            metadata={
                "differential": {"status": "NOT_CALCULABLE"},
                "inrush": {"status": "NOT_INDICATED"},
            },
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "current_increase": True,
            "detectors": {
                "ct_saturation": {
                    "status": "POSSIBLE",
                    "suspects": [{"channel": "IA", "role": "IA"}],
                }
            },
        },
    )
    xfmr = next(h for h in rca.hypotheses if h.hypothesis_id == "TRANSFORMER_INTERNAL_FAULT")
    assert xfmr.status == "PROBABLE"
    assert "through_fault_excluded" in xfmr.missing_evidence


def test_rca_xfmr_through_fault_high_restraint_not_excluded():
    """Borderline Id near characteristic (through-fault / CT mismatch look) stays unconfirmed."""
    fault = FaultClassificationResult(
        fault_type="ABC", status="CLASSIFIED", confidence="MEDIUM"
    )
    assessments = [
        ProtectionAssessment(
            element="87T",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["d"],
            confidence="MEDIUM",
            metadata={
                "differential": {
                    "status": "OK",
                    "operate_a": 3.1,
                    "restraint_a": 10.0,
                    "threshold_a": 3.2,  # just below trip — operate_expected False path
                    "pickup_a": 0.2,
                    "slope": 0.3,
                    "operate_expected": False,
                }
            },
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={"current_increase": True},
    )
    xfmr = next(h for h in rca.hypotheses if h.hypothesis_id == "TRANSFORMER_INTERNAL_FAULT")
    assert "through_fault_excluded" in xfmr.missing_evidence
