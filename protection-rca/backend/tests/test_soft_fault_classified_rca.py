"""UNKNOWN phase type still unlocks matrix fault_classified when protection trips."""

from __future__ import annotations

from consistency.engine import ConsistencyResult
from fault_analysis import FaultClassificationResult
from protection.models import ProtectionAssessment
from rca import HypothesisEngine


def test_soft_fault_classified_for_87t_unknown_type():
    fault = FaultClassificationResult(
        fault_type="UNKNOWN",
        status="INCONCLUSIVE",
        confidence="LOW",
        evidence={
            "available": False,
            "event_classification": {"event_class": "FAULT", "status": "CLASSIFIED"},
        },
        distance={"status": "NOT_APPLICABLE"},
        event_class="FAULT",
        event_class_status="CLASSIFIED",
    )
    assessments = [
        ProtectionAssessment(
            element="87T",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="TRIPPED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            confidence="MEDIUM",
            evidence_ids=["digital:DIFF TRIP"],
        )
    ]
    eng = HypothesisEngine()
    bag = eng._collect_evidence(
        fault,
        assessments,
        ConsistencyResult(summary_status="CONSISTENT", findings=[]),
        {"event_class": "FAULT", "fault_indicated": True},
    )
    assert "fault_classified" in bag
    assert "transformer_diff_operated" in bag or "differential_operated" in bag
