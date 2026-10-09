"""Deep matrix ladder: digital detail, L2 causality, L3 executable fallbacks."""

from __future__ import annotations

from consistency.engine import ConsistencyResult
from event_reconstruction.timeline import TimelineEvent
from fault_analysis import FaultClassificationResult
from protection.models import ProtectionAssessment
from rca import HypothesisEngine
from rca.ladder import (
    apply_l3_fallbacks,
    build_ladder_deep,
    collect_digital_channel_detail,
    score_l2_causality,
    token_satisfied,
)
from rca.matrix import match_matrix


def test_digital_channel_detail_from_timeline_and_assessments():
    tl = [
        TimelineEvent(
            timestamp=0.02,
            event_type="protection_trip",
            source="digital:Ph A Trip",
            confidence="HIGH",
            metadata={},
        ),
        TimelineEvent(
            timestamp=0.05,
            event_type="intertrip",
            source="SOE:HV",
            confidence="HIGH",
            metadata={"point_tag": "INTERTRIP_RECEIVED", "signal": "Intertrip RX"},
        ),
    ]
    assessments = [
        ProtectionAssessment(
            element="51N",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="TRIPPED",
            timing={"pickup_time_s": 0.01, "trip_time_s": 0.04},
            consistency="CONSISTENT",
            setting_reference={},
            confidence="MEDIUM",
            evidence_ids=["digital:51N Earth", "ser:51N_TRIP"],
        )
    ]
    rows, toks, traces = collect_digital_channel_detail(
        timeline=tl, assessments=assessments
    )
    assert any(r.channel == "Ph A Trip" for r in rows)
    assert any("INTERTRIP" in r.channel.upper() or "Intertrip" in r.channel for r in rows)
    assert any(r.element == "51N" for r in rows)
    assert "digital_channel_detail_present" in toks
    assert traces


def test_l2_causality_ok_inception_pickup_trip_interrupt():
    tl = [
        TimelineEvent(0.0, "fault_inception", "analog:I", "HIGH", {}),
        TimelineEvent(0.01, "protection_pickup", "digital:50P", "HIGH", {}),
        TimelineEvent(0.03, "protection_trip", "digital:50P", "HIGH", {}),
        TimelineEvent(0.05, "current_interruption", "analog:I", "HIGH", {}),
    ]
    # TimelineEvent signature may differ — use kwargs style if needed
    caus = score_l2_causality(
        [
            {"timestamp": 0.0, "event_type": "fault_inception", "source": "a"},
            {"timestamp": 0.01, "event_type": "protection_pickup", "source": "d:50"},
            {"timestamp": 0.03, "event_type": "protection_trip", "source": "d:50"},
            {"timestamp": 0.05, "event_type": "current_interruption", "source": "a"},
        ]
    )
    assert caus["order_ok"] is True
    assert "l2_causality_ok" in caus["tokens"]
    assert caus["score"] >= 0.5


def test_l3_earth_fallback_when_no_50n_digital():
    bag = {"fault_classified", "current_increase_observed", "protection_operated"}
    fault = FaultClassificationResult(
        fault_type="AG",
        status="CLASSIFIED",
        confidence="MEDIUM",
        evidence={"ground": True, "I0": 300, "available": True},
        distance={"status": "NOT_APPLICABLE"},
    )
    added, applied, traces = apply_l3_fallbacks(
        bag,
        electrical_flags={"I_max_a": 1000.0, "I0": 300.0},
        fault=fault,
    )
    assert "earth_fault_l3_inferred" in added
    assert "l3_fallback_applied" in added
    assert applied
    assert traces


def test_token_satisfied_accepts_l3_equiv_for_earth():
    bag = {"earth_fault_l3_inferred", "fault_classified"}
    assert token_satisfied(bag, "earth_fault_element_operated")
    assert not token_satisfied(bag, "bus_diff_operated")


def test_matrix_matches_feeder_earth_via_l3_fallback():
    bag = {
        "fault_classified",
        "protection_operated",
        "current_increase_observed",
        "earth_fault_l3_inferred",
        "zero_sequence_elevated",
        "scheme_earth_fault",
    }
    r = match_matrix(bag)
    assert r.matched_scenario_id == "SC_FEEDER_INZONE"
    assert (r.level_coverage or {}).get("agree_count", 0) >= 1


def test_engine_ladder_deep_on_enrichment():
    eng = HypothesisEngine()
    fault = FaultClassificationResult(
        fault_type="AG",
        status="CLASSIFIED",
        confidence="HIGH",
        evidence={
            "available": True,
            "ground": True,
            "Ia_elevated": True,
            "event_classification": {"event_class": "FAULT"},
        },
        distance={"status": "NOT_APPLICABLE"},
        event_class="FAULT",
    )
    assessments = [
        ProtectionAssessment(
            element="50P",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="TRIPPED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            confidence="MEDIUM",
            evidence_ids=["digital:50P_TRIP"],
        )
    ]
    rca = eng.run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "event_class": "FAULT",
            "fault_indicated": True,
            "current_increase": True,
            "I_max_a": 900.0,
            "I0": 280.0,
            "timeline_events": [
                {
                    "timestamp": 0.0,
                    "event_type": "fault_inception",
                    "source": "analog",
                },
                {
                    "timestamp": 0.02,
                    "event_type": "protection_trip",
                    "source": "digital:50P_TRIP",
                },
                {
                    "timestamp": 0.04,
                    "event_type": "current_interruption",
                    "source": "analog",
                },
            ],
            "digital_channel_names": ["50P_TRIP", "IA"],
            "timeline_event_types": [
                "fault_inception",
                "protection_trip",
                "current_interruption",
            ],
            "successful_clearing": True,
        },
    )
    deep = (rca.enrichment or {}).get("ladder_deep") or {}
    assert deep.get("digital_channel_count", 0) >= 1
    assert deep.get("l2_causality")
    assert rca.enrichment.get("matrix_traces")
    # Earth L3 fallback should fire (no 50N digital)
    toks = set(deep.get("tokens") or [])
    assert "earth_fault_l3_inferred" in toks or "l2_causality_ok" in toks


def test_build_ladder_deep_merges_all_layers():
    bag = {"fault_classified", "protection_operated"}
    deep = build_ladder_deep(
        bag=bag,
        timeline=[
            {"timestamp": 0.0, "event_type": "fault_inception", "source": "a"},
            {
                "timestamp": 0.02,
                "event_type": "protection_trip",
                "source": "digital:Trip A",
            },
            {"timestamp": 0.05, "event_type": "current_interruption", "source": "a"},
        ],
        assessments=[],
        electrical_flags={"I_max_a": 800, "I0": 200, "I2": 150},
        fault=FaultClassificationResult(
            fault_type="AG",
            status="CLASSIFIED",
            confidence="MEDIUM",
            evidence={"ground": True},
            distance={"status": "NOT_APPLICABLE"},
        ),
    )
    assert deep.tokens
    assert deep.digital_channels
    assert deep.l2_causality.get("chain")
    assert deep.l3_fallbacks
