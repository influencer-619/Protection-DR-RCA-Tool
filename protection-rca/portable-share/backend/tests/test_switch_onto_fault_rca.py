"""Switch-onto-fault (SOTF) RCA hypothesis — distinct from energization / motor start."""

from __future__ import annotations

from consistency.engine import ConsistencyResult
from fault_analysis import FaultClassificationResult
from protection.models import ProtectionAssessment
from rca import HypothesisEngine


def _fault_classified(ft: str = "AG") -> FaultClassificationResult:
    return FaultClassificationResult(
        fault_type=ft,
        status="CLASSIFIED",
        confidence="HIGH",
        evidence={
            "available": True,
            "event_classification": {"event_class": "FAULT", "status": "CLASSIFIED"},
            "Ia_elevated": True,
            "ground": True,
        },
        distance={"status": "NOT_APPLICABLE"},
        event_class="FAULT",
        event_class_status="CLASSIFIED",
    )


def _trip_oc() -> list[ProtectionAssessment]:
    return [
        ProtectionAssessment(
            element="50",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="TRIPPED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["50_TRIP"],
        )
    ]


def test_sotf_primary_with_sotf_digital_and_trip():
    eng = HypothesisEngine()
    rca = eng.run(
        fault=_fault_classified(),
        assessments=_trip_oc(),
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "event_class": "FAULT",
            "fault_indicated": True,
            "current_increase": True,
            "trip_command": True,
            "digital_channel_names": ["SOTF", "50_TRIP", "52a"],
            "breaker_close": True,
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "SWITCH_ONTO_FAULT"
    assert "switch onto fault" in (rca.primary.title or "").lower()
    stmt = (rca.primary.statement or "").lower()
    assert "sotf" in stmt or "switch onto fault" in stmt


def test_sotf_with_breaker_close_and_trip_without_named_sotf():
    eng = HypothesisEngine()
    rca = eng.run(
        fault=_fault_classified("AB"),
        assessments=_trip_oc(),
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "event_class": "FAULT",
            "fault_indicated": True,
            "current_increase": True,
            "trip_command": True,
            "breaker_close": True,
            "timeline_event_types": ["52a_change", "protection_trip", "fault_inception"],
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "SWITCH_ONTO_FAULT"
    bag = eng._collect_evidence(
        _fault_classified("AB"),
        _trip_oc(),
        ConsistencyResult(summary_status="CONSISTENT"),
        {
            "event_class": "FAULT",
            "breaker_close": True,
            "current_increase": True,
            "timeline_event_types": ["52a_change"],
        },
    )
    assert "breaker_close_observed" in bag
    assert "switch_onto_fault_possible" in bag


def test_52a_change_alone_is_not_breaker_close_or_sotf():
    """Trip/open 52a must not invent Switch onto fault (common HV clearance case)."""
    eng = HypothesisEngine()
    bag = eng._collect_evidence(
        _fault_classified("ABC"),
        _trip_oc(),
        ConsistencyResult(summary_status="CONSISTENT"),
        {
            "event_class": "FAULT",
            "fault_indicated": True,
            "current_increase": True,
            "trip_command": True,
            "timeline_event_types": ["52a_change", "protection_trip", "fault_inception"],
        },
    )
    assert "breaker_close_observed" not in bag
    assert "switch_onto_fault_possible" not in bag

    rca = eng.run(
        fault=_fault_classified("ABC"),
        assessments=_trip_oc(),
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "event_class": "FAULT",
            "fault_indicated": True,
            "current_increase": True,
            "trip_command": True,
            "timeline_event_types": ["52a_change", "protection_trip", "fault_inception"],
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id != "SWITCH_ONTO_FAULT"


def _assess_oc_and_bf() -> list[ProtectionAssessment]:
    return [
        *_trip_oc(),
        ProtectionAssessment(
            element="50BF",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="TRIPPED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["50BF_TRIP"],
        ),
    ]


def test_local_bf_with_current_persist_not_sotf():
    """True local BF (50BF + current still flowing) is Breaker failure, not SOTF."""
    rca = HypothesisEngine().run(
        fault=_fault_classified("ABC"),
        assessments=_assess_oc_and_bf(),
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "event_class": "FAULT",
            "fault_indicated": True,
            "current_increase": True,
            "trip_command": True,
            "current_persists": True,
            "timeline_event_types": ["52a_change", "protection_trip"],
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "BREAKER_FAILURE"
    assert rca.primary.hypothesis_id != "SWITCH_ONTO_FAULT"


def test_hv_clearance_with_50bf_digital_is_zone_fault_not_bf_or_sotf():
    """Upstream HV clearance: 50BF may assert, but local breaker cleared — not BF/SOTF."""
    rca = HypothesisEngine().run(
        fault=_fault_classified("ABC"),
        assessments=_assess_oc_and_bf(),
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "event_class": "FAULT",
            "fault_indicated": True,
            "current_increase": True,
            "trip_command": True,
            # No current_persists — breaker cleared
            "timeline_event_types": ["52a_change", "protection_trip", "current_interruption"],
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id not in ("SWITCH_ONTO_FAULT", "BREAKER_FAILURE")
    assert rca.primary.hypothesis_id in (
        "INTERNAL_FEEDER_FAULT",
        "EXTERNAL_LINE_FAULT",
    )


def test_inrush_pickup_not_sotf():
    """Energization / H2 + pickup-only must stay SWITCHING_TRANSIENT, not SOTF."""
    fault = FaultClassificationResult(
        fault_type="UNKNOWN",
        status="INCONCLUSIVE",
        confidence="LOW",
        evidence={
            "available": True,
            "event_classification": {"event_class": "ENERGIZATION"},
        },
        distance={"status": "NOT_APPLICABLE"},
        event_class="ENERGIZATION",
        event_class_status="PROBABLE",
    )
    assessments = [
        ProtectionAssessment(
            element="87T",
            enabled=None,
            pickup=True,
            trip=False,
            expected_operation="UNKNOWN",
            actual_operation="PICKED_UP",
            timing=None,
            consistency="UNVERIFIABLE",
            setting_reference={},
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "event_class": "ENERGIZATION",
            "detectors": {"magnetizing_inrush": {"status": "POSSIBLE"}},
            "current_increase": True,
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "SWITCHING_TRANSIENT"
    assert rca.primary.hypothesis_id != "SWITCH_ONTO_FAULT"
    sotf = next((h for h in rca.hypotheses if h.hypothesis_id == "SWITCH_ONTO_FAULT"), None)
    assert sotf is None or sotf.score < rca.primary.score


def test_title_and_yaml_load():
    eng = HypothesisEngine()
    ids = {h.get("id") for h in eng.hypothesis_defs}
    assert "SWITCH_ONTO_FAULT" in ids
    from rca import _title

    assert _title("SWITCH_ONTO_FAULT") == "Switch onto fault"


def test_autoreclose_after_trip_is_not_primary_sotf():
    """Feeder/line fault with 79 AR reclaim must stay zone fault, not Switch onto fault."""
    assessments = [
        *_trip_oc(),
        ProtectionAssessment(
            element="79",
            enabled=True,
            pickup=True,
            trip=False,
            expected_operation="UNKNOWN",
            actual_operation="PICKED_UP",
            timing={"reclose_shots": 1},
            consistency="UNVERIFIABLE",
            setting_reference={},
            evidence_ids=["79_AR"],
        ),
    ]
    rca = HypothesisEngine().run(
        fault=_fault_classified("AG"),
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "event_class": "FAULT",
            "fault_indicated": True,
            "current_increase": True,
            "trip_command": True,
            # No breaker_close — AR alone must not invent SOTF
            "timeline_event_types": [
                "fault_inception",
                "protection_trip",
                "reclose",
            ],
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id != "SWITCH_ONTO_FAULT"
    assert rca.primary.hypothesis_id in (
        "INTERNAL_FEEDER_FAULT",
        "EXTERNAL_LINE_FAULT",
    )
