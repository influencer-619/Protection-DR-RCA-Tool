"""Transformer charging / magnetizing inrush must not frame as AG + 87 internal fault."""

from __future__ import annotations

from common.results import ALGORITHM_VERSION, SignalResult
from consistency.engine import ConsistencyResult
from electrical_analysis.analyzer import ElectricalAnalysisResult
from fault_analysis import FaultClassificationResult, classify_fault
from protection.models import ProtectionAssessment
from rca import HypothesisEngine, _scheme_tokens_from_assessments


def _sr(mag: float, channel: str = "x") -> SignalResult:
    return SignalResult(
        value=mag,
        unit="A",
        timestamp=0.0,
        method="test",
        algorithm_version=ALGORITHM_VERSION,
        input_channels=[channel],
        quality="GOOD",
        status="OK",
    )


def test_inrush_suppresses_phase_fault_type():
    rms = {k: _sr(v, k) for k, v in (("IA", 5.0), ("IB", 0.5), ("IC", 0.5))}
    elec = ElectricalAnalysisResult(
        record_id="chg",
        nominal_frequency_hz=50.0,
        sample_rate_hz=1000.0,
        rms=rms,
        channel_roles={"IA": "IA", "IB": "IB", "IC": "IC"},
        detectors={
            "magnetizing_inrush": {
                "status": "POSSIBLE",
                "channels": [{"channel": "IA", "h2_ratio": 0.45}],
            }
        },
    )
    result = classify_fault(elec, digital_channel_names=["Diff picked up"])
    assert result.fault_type == "UNKNOWN"
    assert result.status == "INCONCLUSIVE"
    assert result.event_class == "ENERGIZATION"
    assert result.evidence.get("ground") is None
    assert result.evidence.get("ground_applicable") is False
    assert any(
        "inrush" in (lim or "").lower() or "energization" in (lim or "").lower()
        for lim in result.limitations
    )


def test_xfmr_pickup_only_not_diff_operated_token():
    a = ProtectionAssessment(
        element="87T",
        enabled=None,
        pickup=True,
        trip=False,
        expected_operation="UNKNOWN",
        actual_operation="PICKED_UP",
        timing=None,
        consistency="UNVERIFIABLE",
        setting_reference={},
        evidence_ids=["87_PICKUP"],
    )
    toks = _scheme_tokens_from_assessments([a])
    assert "transformer_diff_picked_up" in toks
    assert "transformer_diff_operated" not in toks
    assert "differential_operated" not in toks


def test_earth_fault_pickup_not_said_operated():
    """EF pickup-only must name exact code (51N) — never invent 67N / say operated."""
    a = ProtectionAssessment(
        element="51N",
        enabled=None,
        pickup=True,
        trip=False,
        expected_operation="UNKNOWN",
        actual_operation="PICKED_UP",
        timing=None,
        consistency="UNVERIFIABLE",
        setting_reference={},
        evidence_ids=["51N_PICKUP"],
    )
    toks = _scheme_tokens_from_assessments([a])
    assert "earth_fault_element_picked_up" in toks
    assert "earth_fault_element_operated" not in toks

    fault = FaultClassificationResult(
        fault_type="AG",
        status="CLASSIFIED",
        confidence="MEDIUM",
        evidence={"available": True, "ground": True},
        distance={"status": "NOT_APPLICABLE"},
        limitations=[],
    )
    cons = ConsistencyResult(summary_status="CONSISTENT")
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=[a],
        consistency=cons,
        electrical_flags={"current_increase": True, "fault_indicated": True},
    )
    feeder = next(
        (h for h in rca.hypotheses if h.hypothesis_id == "INTERNAL_FEEDER_FAULT"),
        None,
    )
    assert feeder is not None
    stmt = (feeder.statement or "").lower()
    assert "51n" in stmt
    assert "pickup" in stmt
    assert "67n" not in stmt
    assert "50n/51n/67n" not in stmt
    assert "operated" not in stmt or "pickup" in stmt


def test_earth_fault_rca_lists_exact_tripped_codes():
    """50N+51N trip narrative must say 50N, 51N — not the 50N/51N/67N family label."""
    asses = [
        ProtectionAssessment(
            element="50N",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["50N_TRIP"],
        ),
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
            evidence_ids=["51N_TRIP"],
        ),
    ]
    fault = FaultClassificationResult(
        fault_type="AG",
        status="CLASSIFIED",
        confidence="HIGH",
        evidence={"available": True, "ground": True},
        distance={"status": "NOT_APPLICABLE"},
        limitations=[],
    )
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=asses,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={"current_increase": True, "fault_indicated": True},
    )
    feeder = next(
        (h for h in rca.hypotheses if h.hypothesis_id == "INTERNAL_FEEDER_FAULT"),
        None,
    )
    assert feeder is not None
    stmt = feeder.statement or ""
    assert "50N" in stmt and "51N" in stmt
    assert "67N" not in stmt
    assert "50N/51N/67N" not in stmt
    assert "pickup with trip" in stmt.lower()


def test_protection_evidence_says_pickup_not_or_trip():
    """Pickup-only must label as pickup; both as pickup with trip; trip-only as trip."""
    from rca import HypothesisEngine

    fault = FaultClassificationResult(
        fault_type="UNKNOWN",
        status="INCONCLUSIVE",
        confidence="LOW",
        evidence={"available": True},
        distance={"status": "NOT_APPLICABLE"},
        limitations=[],
    )
    cons = ConsistencyResult(summary_status="CONSISTENT")
    eng = HypothesisEngine()

    pickup_only = [
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
            evidence_ids=["87_PICKUP"],
        )
    ]
    rca_p = eng.run(fault=fault, assessments=pickup_only, consistency=cons, electrical_flags={})
    bag_p = eng._collect_evidence(fault, pickup_only, cons, {})
    assert "protection_pickup_asserted" in bag_p
    assert "protection_pickup_with_trip" not in bag_p
    assert "protection_operated" not in bag_p
    assert any(
        "protection_pickup_asserted" in (h.supporting_evidence or [])
        for h in rca_p.hypotheses
    )

    both = [
        ProtectionAssessment(
            element="51",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["51_TRIP"],
        )
    ]
    bag_b = eng._collect_evidence(fault, both, cons, {})
    assert "protection_pickup_with_trip" in bag_b
    assert "protection_operated" in bag_b

    trip_only = [
        ProtectionAssessment(
            element="50",
            enabled=True,
            pickup=False,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["50_TRIP"],
        )
    ]
    bag_t = eng._collect_evidence(fault, trip_only, cons, {})
    assert "protection_trip_asserted" in bag_t
    assert "protection_pickup_asserted" not in bag_t


def test_rca_inrush_statement_omits_87_when_only_oc_pickup():
    """H2 inrush + 50 pickup must not invent '87 pickup without trip' in RCA text."""
    fault = FaultClassificationResult(
        fault_type="UNKNOWN",
        status="INCONCLUSIVE",
        confidence="LOW",
        evidence={"available": True},
        distance={"status": "NOT_APPLICABLE"},
        limitations=["Magnetizing inrush"],
    )
    assessments = [
        ProtectionAssessment(
            element="50",
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
    cons = ConsistencyResult(summary_status="NOT_AVAILABLE")
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=cons,
        electrical_flags={
            "detectors": {"magnetizing_inrush": {"status": "POSSIBLE"}},
            "current_increase": True,
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "SWITCHING_TRANSIENT"
    stmt = (rca.primary.statement or "").lower()
    assert "87" not in stmt
    assert "overcurrent pickup" in stmt or "elevated h2" in stmt


def test_rca_inrush_statement_mentions_87_only_when_diff_picked_up():
    fault = FaultClassificationResult(
        fault_type="UNKNOWN",
        status="INCONCLUSIVE",
        confidence="LOW",
        evidence={"available": True},
        distance={"status": "NOT_APPLICABLE"},
        limitations=["Magnetizing inrush"],
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
            evidence_ids=["87_PICKUP"],
        )
    ]
    cons = ConsistencyResult(summary_status="CONSISTENT")
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=cons,
        electrical_flags={
            "detectors": {"magnetizing_inrush": {"status": "POSSIBLE"}},
            "current_increase": True,
        },
    )
    assert rca.primary is not None
    assert "87 pickup without trip" in (rca.primary.statement or "").lower()


def test_rca_prefers_energization_over_internal_fault_on_inrush_pickup():
    fault = FaultClassificationResult(
        fault_type="UNKNOWN",
        status="INCONCLUSIVE",
        confidence="LOW",
        evidence={"available": True},
        distance={"status": "NOT_APPLICABLE"},
        limitations=["Magnetizing inrush"],
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
    cons = ConsistencyResult(summary_status="CONSISTENT")
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=cons,
        electrical_flags={
            "detectors": {"magnetizing_inrush": {"status": "POSSIBLE"}},
            "current_increase": True,
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "SWITCHING_TRANSIENT"
    assert rca.primary.hypothesis_id != "TRANSFORMER_INTERNAL_FAULT"
    assert all(
        h.hypothesis_id != "TRANSFORMER_INTERNAL_FAULT" or h.score < rca.primary.score
        for h in rca.hypotheses
    )
