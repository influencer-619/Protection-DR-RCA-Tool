"""Excel L1→L2→L3 ladder: bag tokens from digitals/SOE/DR + matrix prefer."""

from __future__ import annotations

from consistency.engine import ConsistencyResult
from fault_analysis import FaultClassificationResult
from protection.models import ProtectionAssessment
from rca import HypothesisEngine
from rca.matrix import layer_tokens_present, match_matrix


def _fault_abc() -> FaultClassificationResult:
    return FaultClassificationResult(
        fault_type="ABC",
        status="CLASSIFIED",
        confidence="HIGH",
        evidence={
            "available": True,
            "event_classification": {"event_class": "FAULT"},
            "Ia_elevated": True,
            "Ib_elevated": True,
            "Ic_elevated": True,
            "ground": False,
            "I2": 200.0,
        },
        distance={"status": "NOT_APPLICABLE"},
        event_class="FAULT",
    )


def _trip(el: str) -> ProtectionAssessment:
    return ProtectionAssessment(
        element=el,
        enabled=True,
        pickup=True,
        trip=True,
        expected_operation="OPERATE",
        actual_operation="TRIPPED",
        timing=None,
        consistency="CONSISTENT",
        setting_reference={},
        confidence="MEDIUM",
        evidence_ids=[f"digital:{el}"],
    )


def test_layer_tokens_present_splits_l1_l2_l3():
    bag = {
        "protection_operated",
        "successful_clearing",
        "fault_classified",
        "negative_sequence_elevated",
    }
    cov = layer_tokens_present(bag)
    assert cov["L1"] is True
    assert cov["L2"] is True
    assert cov["L3"] is True


def test_collect_evidence_emits_sequence_and_clearing_tokens():
    eng = HypothesisEngine()
    bag = eng._collect_evidence(
        _fault_abc(),
        [_trip("50P"), _trip("51P")],
        ConsistencyResult(summary_status="CONSISTENT"),
        {
            "event_class": "FAULT",
            "fault_indicated": True,
            "current_increase": True,
            "I_max_a": 1000.0,
            "I2": 250.0,
            "I0": 20.0,
            "V_min_v": 40.0,
            "V_max_v": 110.0,
            "timeline_event_types": [
                "protection_trip",
                "current_interruption",
                "fault_inception",
            ],
            "successful_clearing": True,
            "breaker_open_confirmed": True,
        },
    )
    assert "negative_sequence_elevated" in bag
    assert "voltage_sag_observed" in bag
    assert "successful_clearing" in bag
    assert "breaker_open_confirmed" in bag
    assert "fault_inception_observed" in bag
    assert "evidence_l1_present" in bag
    assert "evidence_l3_present" in bag


def test_matrix_match_records_ladder_and_prefers_multilayer():
    bag = {
        "fault_classified",
        "protection_operated",
        "earth_fault_element_operated",
        "current_increase_observed",
        "scheme_earth_fault",
        "successful_clearing",
        "breaker_open_confirmed",
    }
    r = match_matrix(bag)
    assert r.matched_scenario_id == "SC_FEEDER_INZONE"
    assert (r.level_coverage or {}).get("agree_count", 0) >= 2
    assert r.prefer_primary is True
    assert any("ladder" in t.lower() or "L1" in t for t in r.traces)


def test_unknown_event_class_does_not_force_no_fault_in_engine():
    """Pipeline/engine alignment: UNKNOWN must not suppress fault_classified."""
    eng = HypothesisEngine()
    fault = FaultClassificationResult(
        fault_type="AG",
        status="CLASSIFIED",
        confidence="MEDIUM",
        evidence={"available": True, "ground": True, "Ia_elevated": True},
        distance={"status": "NOT_APPLICABLE"},
        event_class="UNKNOWN",
    )
    bag = eng._collect_evidence(
        fault,
        [_trip("50N")],
        ConsistencyResult(summary_status="CONSISTENT"),
        {"event_class": "UNKNOWN", "current_increase": True, "I_max_a": 800, "I0": 300},
    )
    assert "electrical_no_fault" not in bag
    assert "fault_classified" in bag
