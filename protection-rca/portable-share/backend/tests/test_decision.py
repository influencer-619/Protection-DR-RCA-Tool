"""Decision engine — CONFIRMED vs WITH_WARNINGS gating."""

from __future__ import annotations

from consistency.engine import ConsistencyResult
from decision import DecisionEngine, is_material_decision_warning
from fault_analysis import FaultClassificationResult
from protection.models import ProtectionAssessment
from rca import HypothesisEngine


def _feeder_confirmed_rca():
    fault = FaultClassificationResult(
        fault_type="AG", status="CLASSIFIED", confidence="MEDIUM", evidence={"ground": True}
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
    return HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={"current_increase": True},
    )


def test_informational_limits_do_not_downgrade_confirmed():
    rca = _feeder_confirmed_rca()
    assert rca.primary is not None
    assert rca.primary.status == "CONFIRMED"
    d = DecisionEngine().decide(
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        rca=rca,
        warnings=[
            "loop_BC: NOT AVAILABLE — missing V/I for BC",
            "Location NOT APPLICABLE for this scheme",
        ],
    )
    assert d.state == "ANALYSIS_COMPLETE"
    assert any("CONFIRMED" in r for r in d.reasons)


def test_material_warning_downgrades_confirmed():
    rca = _feeder_confirmed_rca()
    d = DecisionEngine().decide(
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        rca=rca,
        warnings=["CT saturation POSSIBLE on some channels"],
    )
    assert d.state == "ANALYSIS_COMPLETE_WITH_WARNINGS"


def test_probable_stays_with_warnings():
    from rca import RCAResult, HypothesisResult

    rca = RCAResult(
        primary=HypothesisResult(
            hypothesis_id="INTERNAL_FEEDER_FAULT",
            status="PROBABLE",
            score=0.7,
            confidence="MEDIUM",
        )
    )
    d = DecisionEngine().decide(rca=rca, warnings=[])
    assert d.state == "ANALYSIS_COMPLETE_WITH_WARNINGS"


def test_material_classifier():
    assert is_material_decision_warning("CT saturation POSSIBLE") is True
    assert is_material_decision_warning("loop_AB: NOT AVAILABLE — missing V/I") is False
    assert is_material_decision_warning("FAULT DISTANCE: NOT CALCULABLE") is False
    assert (
        is_material_decision_warning("Merged 1 external timeline events from SOE / event report")
        is False
    )


def test_soe_merge_note_keeps_confirmed_complete():
    rca = _feeder_confirmed_rca()
    d = DecisionEngine().decide(
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        rca=rca,
        warnings=["Merged 1 external timeline events from SOE / event report"],
    )
    assert d.state == "ANALYSIS_COMPLETE"
