"""IEEE/PSRC-style DFR event class: FAULT gate before AG/AB typing."""

from __future__ import annotations

from common.results import ALGORITHM_VERSION, SignalResult
from electrical_analysis.analyzer import ElectricalAnalysisResult
from fault_analysis import classify_fault
from fault_analysis.event_class import EventClass, classify_dfr_event
from protection.models import ProtectionAssessment


def _sr(mag: float, channel: str = "x", unit: str = "A") -> SignalResult:
    return SignalResult(
        value=mag,
        unit=unit,
        timestamp=0.0,
        method="test",
        algorithm_version=ALGORITHM_VERSION,
        input_channels=[channel],
        quality="GOOD",
        status="OK",
    )


def _elec_i(
    ia: float,
    ib: float,
    ic: float,
    *,
    detectors: dict | None = None,
    va: float | None = None,
) -> ElectricalAnalysisResult:
    rms = {
        "IA": _sr(ia, "IA"),
        "IB": _sr(ib, "IB"),
        "IC": _sr(ic, "IC"),
    }
    roles = {"IA": "IA", "IB": "IB", "IC": "IC"}
    if va is not None:
        rms["VA"] = _sr(va, "VA", unit="V")
        rms["VB"] = _sr(va, "VB", unit="V")
        rms["VC"] = _sr(va, "VC", unit="V")
        roles.update({"VA": "VA", "VB": "VB", "VC": "VC"})
    return ElectricalAnalysisResult(
        record_id="dfr",
        nominal_frequency_hz=50.0,
        sample_rate_hz=1000.0,
        rms=rms,
        channel_roles=roles,
        detectors=detectors or {},
    )


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


def test_energization_from_h2_no_trip():
    elec = _elec_i(
        5.0,
        0.5,
        0.5,
        detectors={
            "magnetizing_inrush": {
                "status": "POSSIBLE",
                "channels": [{"channel": "IA", "h2_ratio": 0.45}],
            }
        },
    )
    dfr = classify_dfr_event(elec, assessments=[_pu("87T")])
    assert dfr.event_class == EventClass.ENERGIZATION
    result = classify_fault(elec, assessments=[_pu("87T")])
    assert result.event_class == EventClass.ENERGIZATION
    assert result.fault_type == "UNKNOWN"
    assert result.status == "INCONCLUSIVE"


def test_motor_start_class():
    elec = _elec_i(8.0, 7.5, 0.4, detectors={"active_bay_prefixes": ["START"]})
    result = classify_fault(
        elec,
        digital_channel_names=["Start I>1", "Any Start", "Thermal Alarm"],
        assessments=[_pu("51"), _pu("46")],
    )
    assert result.event_class == EventClass.MOTOR_START
    assert result.fault_type == "UNKNOWN"


def test_motor_start_not_fault_when_voltage_sags():
    """EVT-17 style: 46/51 pickup-only + V sag must stay MOTOR_START, not FAULT."""
    elec = _elec_i(
        8.0,
        7.5,
        0.4,
        va=40.0,
        detectors={"active_bay_prefixes": ["START"]},
    )
    timeline = [
        {"event_type": "current_increase", "timestamp": 0.10},
        {
            "event_type": "voltage_change",
            "timestamp": 0.10,
            "metadata": {"baseline_rms": 63.5, "value_rms": 35.0},
        },
        {"event_type": "protection_pickup", "timestamp": 0.12, "source": "digital:Start I>1"},
    ]
    dfr = classify_dfr_event(
        elec,
        timeline=timeline,
        digital_channel_names=["Start I>1", "Any Start", "Thermal Alarm"],
        assessments=[_pu("51"), _pu("46")],
    )
    assert dfr.event_class == EventClass.MOTOR_START
    assert dfr.event_class != EventClass.FAULT
    result = classify_fault(
        elec,
        timeline=timeline,
        digital_channel_names=["Start I>1", "Any Start", "Thermal Alarm"],
        assessments=[_pu("51"), _pu("46")],
    )
    assert result.event_class == EventClass.MOTOR_START
    assert result.fault_type == "UNKNOWN"
    assert result.evidence.get("ground") is None


def test_switching_class_from_52a_without_trip():
    elec = _elec_i(3.0, 3.0, 3.0)
    timeline = [
        {"event_type": "current_increase", "source": "analog"},
        {"event_type": "52a_change", "source": "digital:52a Stn_Unit_Tie"},
    ]
    dfr = classify_dfr_event(
        elec,
        timeline=timeline,
        digital_channel_names=["52a Stn_Unit_Tie", "CheckSync"],
    )
    assert dfr.event_class == EventClass.SWITCHING
    result = classify_fault(
        elec,
        timeline=timeline,
        digital_channel_names=["52a Stn_Unit_Tie", "CheckSync"],
    )
    assert result.event_class == EventClass.SWITCHING
    assert result.fault_type == "UNKNOWN"


def test_disturbance_current_only_no_ag():
    """Imbalanced I without V sag / trip must not publish AG."""
    elec = _elec_i(5.0, 0.4, 0.4)
    timeline = [{"event_type": "current_increase", "source": "analog"}]
    result = classify_fault(elec, timeline=timeline)
    assert result.event_class == EventClass.DISTURBANCE
    assert result.fault_type == "UNKNOWN"


def test_fault_probable_without_clearance_duration():
    # V + I + trip but no interrupt → FAULT PROBABLE (duration incomplete)
    elec = _elec_i(12.0, 11.0, 0.5, va=10.0)
    timeline = [
        {"event_type": "current_increase", "timestamp": 0.10, "source": "analog"},
        {
            "event_type": "voltage_change",
            "timestamp": 0.10,
            "metadata": {"baseline_rms": 63.5, "value_rms": 20.0},
        },
        {"event_type": "protection_trip", "timestamp": 0.18, "source": "digital:Trip"},
    ]
    dfr = classify_dfr_event(
        elec,
        timeline=timeline,
        assessments=[_pu("50", trip=True)],
    )
    assert dfr.event_class == EventClass.FAULT
    assert dfr.status == "PROBABLE"
    assert dfr.evidence.get("fault_duration_ok") is False


def test_fault_confirmed_with_clearance_duration():
    # Phase-phase elevated currents → AB; CONFIRMED needs clearance duration
    elec = _elec_i(12.0, 11.0, 0.5, va=10.0)
    timeline = [
        {"event_type": "current_increase", "timestamp": 0.10, "source": "analog"},
        {
            "event_type": "voltage_change",
            "timestamp": 0.10,
            "metadata": {"baseline_rms": 63.5, "value_rms": 20.0},
        },
        {"event_type": "protection_trip", "timestamp": 0.18, "source": "digital:Trip"},
        {
            "event_type": "current_interruption",
            "timestamp": 0.22,
            "source": "analog",
        },
    ]
    dfr = classify_dfr_event(
        elec,
        timeline=timeline,
        assessments=[_pu("50", trip=True)],
    )
    assert dfr.event_class == EventClass.FAULT
    assert dfr.status == "CONFIRMED"
    assert dfr.evidence.get("duration_ms") == 120.0
    assert dfr.evidence.get("duration_band") == "TYPICAL"
    assert dfr.evidence.get("fault_duration_ok") is True
    result = classify_fault(
        elec,
        timeline=timeline,
        assessments=[_pu("50", trip=True)],
    )
    assert result.event_class == EventClass.FAULT
    assert result.fault_type == "AB"
    assert result.status in ("CLASSIFIED", "PROBABLE")


def test_long_uncleared_trip_without_v_is_disturbance():
    """Trip + long uncleared span + no V sag → DISTURBANCE (not feeder FAULT)."""
    elec = _elec_i(5.0, 0.4, 0.4)
    timeline = [
        {"event_type": "current_increase", "timestamp": 0.05, "source": "analog"},
        {"event_type": "protection_trip", "timestamp": 1.00, "source": "digital:Trip"},
    ]
    dfr = classify_dfr_event(
        elec,
        timeline=timeline,
        assessments=[_pu("50", trip=True)],
    )
    assert dfr.event_class == EventClass.DISTURBANCE
    assert dfr.evidence.get("duration_ms") == 950.0
    assert dfr.evidence.get("duration_band") == "LONG"
    assert dfr.evidence.get("cleared") is False
    result = classify_fault(
        elec,
        timeline=timeline,
        assessments=[_pu("50", trip=True)],
    )
    assert result.fault_type == "UNKNOWN"
