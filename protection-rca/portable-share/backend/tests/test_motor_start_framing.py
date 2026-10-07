"""Motor-start DRs must not frame as AB feeder faults."""

from __future__ import annotations

from consistency.engine import ConsistencyResult
from fault_analysis import FaultClassificationResult, motor_start_context
from protection.models import ProtectionAssessment
from rca import HypothesisEngine


def _pu(element: str, *, trip: bool = False) -> ProtectionAssessment:
    return ProtectionAssessment(
        element=element,
        enabled=None,
        pickup=True,
        trip=trip,
        expected_operation="UNKNOWN",
        actual_operation="OPERATED" if trip else "PICKED_UP",
        timing=None,
        consistency="UNVERIFIABLE",
        setting_reference={},
    )


def test_motor_start_context_likely_on_start_prefix_and_oc_pickup():
    ctx = motor_start_context(
        ["Start I>1", "Any Start", "Thermal Alarm", "Stall Rotor-run"],
        detectors={"active_bay_prefixes": ["START"]},
        assessments=[_pu("51"), _pu("46")],
    )
    assert ctx["present"] is True
    assert ctx["likely"] is True


def test_rca_primary_is_motor_start_not_feeder_fault():
    fault = FaultClassificationResult(
        fault_type="UNKNOWN",
        status="INCONCLUSIVE",
        confidence="LOW",
        evidence={"available": True},
        distance={"status": "NOT_APPLICABLE"},
        limitations=["Motor start"],
    )
    assessments = [_pu("51"), _pu("46"), ProtectionAssessment(
        element="48",
        enabled=None,
        pickup=None,
        trip=None,
        expected_operation="UNKNOWN",
        actual_operation="UNKNOWN",
        timing=None,
        consistency="UNVERIFIABLE",
        setting_reference={},
    )]
    cons = ConsistencyResult(summary_status="CONSISTENT")
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=cons,
        electrical_flags={
            "detectors": {"active_bay_prefixes": ["START"]},
            "digital_channel_names": [
                "Start I>1",
                "Start I2>1",
                "Any Start",
                "Prolonged Start",
                "Thermal Alarm",
            ],
            "current_increase": True,
        },
    )
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "MOTOR_START"
    assert rca.primary.hypothesis_id != "INTERNAL_FEEDER_FAULT"
    stmt = (rca.primary.statement or "").lower()
    assert "motor" in stmt
    assert "87" not in stmt


def test_classify_fault_suppresses_ab_on_motor_start():
    from common.results import ALGORITHM_VERSION, SignalResult
    from electrical_analysis.analyzer import ElectricalAnalysisResult
    from fault_analysis import classify_fault

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

    rms = {k: _sr(v, k) for k, v in (("IA", 8.0), ("IB", 7.5), ("IC", 0.4))}
    elec = ElectricalAnalysisResult(
        record_id="mtr",
        nominal_frequency_hz=50.0,
        sample_rate_hz=1000.0,
        rms=rms,
        channel_roles={"IA": "IA", "IB": "IB", "IC": "IC"},
        detectors={"active_bay_prefixes": ["START"]},
    )
    result = classify_fault(
        elec,
        digital_channel_names=["Start I>1", "Any Start", "Thermal Alarm"],
        assessments=[_pu("51"), _pu("46")],
    )
    assert result.fault_type == "UNKNOWN"
    assert result.status == "INCONCLUSIVE"
    assert result.event_class == "MOTOR_START"
    assert any(
        "motor start" in (lim or "").lower() or "motor_start" in (lim or "").lower()
        for lim in result.limitations
    )
