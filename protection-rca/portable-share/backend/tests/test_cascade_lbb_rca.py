"""LBB / multi-bay cascade: single-incident BF primary RCA + detect helpers."""

from __future__ import annotations

from consistency.engine import ConsistencyResult
from fault_analysis import FaultClassificationResult
from protection.models import ProtectionAssessment
from rca import HypothesisEngine

from app.services.cascade_lbb import detect_lbb_cascade


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


def _trip_oc_and_bf() -> list[ProtectionAssessment]:
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
        ),
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


def test_detect_lbb_cascade_strong_pattern():
    det = detect_lbb_cascade(
        digital_names=[
            "50_TRIP",
            "50BF",
            "INTERTRIP_SEND",
            "INTERTRIP_RECEIVE",
            "52A",
        ],
        cascade_mode=False,
    )
    assert det["cascade_lbb_detected"] is True
    assert det["bf_element_seen"] is True
    assert det["intertrip_send_seen"] is True
    assert det["intertrip_receive_seen"] is True


def test_detect_lbb_cascade_mode_softens_requirements():
    det = detect_lbb_cascade(
        digital_names=["LBB", "INTERTRIP_RX"],
        cascade_mode=True,
    )
    assert det["cascade_lbb_detected"] is True
    assert det["bf_element_seen"] is True


def test_detect_no_cascade_without_bf_or_intertrip():
    det = detect_lbb_cascade(
        digital_names=["50_TRIP", "51_PICKUP"],
        cascade_mode=False,
    )
    assert det["cascade_lbb_detected"] is False


def test_cascade_lbb_primary_breaker_failure():
    eng = HypothesisEngine()
    rca = eng.run(
        fault=_fault_classified(),
        assessments=_trip_oc_and_bf(),
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "event_class": "FAULT",
            "fault_indicated": True,
            "current_increase": True,
            "trip_command": True,
            "current_persists": True,
            "cascade_lbb_detected": True,
            "intertrip": True,
            "scheme_tokens": ["scheme_breaker_failure", "bf_logic_satisfied"],
            "digital_channel_names": [
                "50_TRIP",
                "50BF",
                "INTERTRIP_SEND",
                "INTERTRIP_RECEIVE",
            ],
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "BREAKER_FAILURE"
    stmt = (rca.primary.statement or "").lower()
    assert "cascade" in stmt or "breaker failure" in stmt or "lbb" in stmt
    # Intertrip must not outrank BF as primary
    inter = next((h for h in rca.hypotheses if h.hypothesis_id == "INTERTRIP_OPERATION"), None)
    if inter is not None:
        assert (inter.score or 0) <= (rca.primary.score or 0)


def test_cascade_evidence_bag_includes_cascade_token():
    eng = HypothesisEngine()
    bag = eng._collect_evidence(
        _fault_classified(),
        _trip_oc_and_bf(),
        ConsistencyResult(summary_status="CONSISTENT"),
        {
            "event_class": "FAULT",
            "cascade_lbb_detected": True,
            "trip_command": True,
            "current_persists": True,
            "intertrip_send_seen": True,
            "scheme_tokens": ["bf_logic_satisfied"],
        },
    )
    assert "cascade_lbb_detected" in bag
    assert "bf_logic_satisfied" in bag
    assert "cascade_upstream_clearance" not in bag


def test_hv_intertrip_receive_primary_is_intertrip_not_feeder():
    """Backup HV bay that received LBB intertrip must not CONFIRMED feeder fault."""
    eng = HypothesisEngine()
    rca = eng.run(
        fault=_fault_classified("ABC"),
        assessments=_trip_oc_and_bf(),
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "event_class": "FAULT",
            "fault_indicated": True,
            "current_increase": True,
            "trip_command": True,
            "intertrip": True,
            "intertrip_receive_seen": True,
            "cascade_upstream_clearance": True,
            "cascade_lbb_detected": True,
            "timeline_event_types": ["protection_trip", "intertrip", "current_interruption"],
            "digital_channel_names": [
                "50P_TRIP",
                "51P_TRIP",
                "50BF",
                "INTERTRIP_RX",
            ],
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "INTERTRIP_OPERATION"
    assert rca.primary.hypothesis_id != "INTERNAL_FEEDER_FAULT"
    stmt = (rca.primary.statement or "").lower()
    assert "intertrip" in stmt or "transfer" in stmt or "upstream" in stmt


def test_local_rx_not_cancelled_by_station_soe_send():
    """HV CFG INTERTRIP_RECEIVED must stay RX even when SOE also lists LV SEND."""
    from app.services.cascade_lbb import classify_intertrip_direction

    d = classify_intertrip_direction(
        digital_names=["INTERTRIP_RECEIVED", "HV_TRIP_CMD"],
        soe_tags=["INTERTRIP_SEND", "INTERTRIP_RECEIVED", "50BF_TRIP_LBB"],
        timeline_events=[
            {
                "event_type": "intertrip",
                "source": "SOE:LV",
                "metadata": {"point_tag": "INTERTRIP_SEND"},
            },
            {
                "event_type": "intertrip",
                "source": "digital:INTERTRIP_RECEIVED",
                "metadata": {"channel": "INTERTRIP_RECEIVED"},
            },
        ],
    )
    assert d["intertrip_receive_seen"] is True
    assert d["intertrip_send_seen"] is False
    assert d["cascade_upstream_clearance"] is True
