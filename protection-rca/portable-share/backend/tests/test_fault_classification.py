"""Unit tests for fault classification."""

from __future__ import annotations

import math

import numpy as np

from common.results import SignalResult, ALGORITHM_VERSION
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


def _elec_from_currents(ia: float, ib: float, ic: float, i0: float | None = None) -> ElectricalAnalysisResult:
    roles = {"IA": "IA", "IB": "IB", "IC": "IC"}
    rms = {k: _sr(v, k) for k, v in (("IA", ia), ("IB", ib), ("IC", ic))}
    elec = ElectricalAnalysisResult(
        record_id="r1",
        nominal_frequency_hz=50.0,
        sample_rate_hz=4000.0,
        rms=rms,
        channel_roles={v: k for k, v in roles.items()},
    )
    if i0 is not None:
        from common.results import SignalResult as SR

        elec.sequences["current_sequences"] = SR(
            value={
                "zero": {"magnitude": i0, "angle_deg": 0, "real": i0, "imag": 0},
                "positive": {"magnitude": max(ia, ib, ic), "angle_deg": 0, "real": 0, "imag": 0},
                "negative": {"magnitude": 0.0, "angle_deg": 0, "real": 0, "imag": 0},
            },
            unit="A",
            timestamp=0.0,
            method="test",
            algorithm_version=ALGORITHM_VERSION,
            input_channels=["IA", "IB", "IC"],
            quality="GOOD",
            status="OK",
        )
    return elec


def test_classify_ag():
    elec = _elec_from_currents(1000, 50, 50, i0=300)
    r = classify_fault(elec)
    assert r.fault_type == "AG"
    assert r.status in ("CLASSIFIED", "PROBABLE")


def test_classify_abc():
    elec = _elec_from_currents(800, 820, 790, i0=5)
    r = classify_fault(elec)
    assert r.fault_type in ("ABC", "ABCG")


def test_insufficient_evidence_unknown():
    elec = ElectricalAnalysisResult(
        record_id="r2", nominal_frequency_hz=50.0, sample_rate_hz=4000.0
    )
    r = classify_fault(elec)
    assert r.fault_type == "UNKNOWN"
    assert r.status in ("UNKNOWN", "INCONCLUSIVE")


def test_distance_not_applicable_without_distance_scheme():
    """OC/EF-style events must not get Z1/km FAULT DISTANCE limitations."""
    elec = _elec_from_currents(1000, 50, 50, i0=300)
    r = classify_fault(elec)
    assert r.distance["status"] == "NOT_APPLICABLE"
    assert r.evidence.get("distance_applicable") is False
    assert not any("FAULT DISTANCE" in x or "Z1" in x for x in r.limitations)


def test_distance_not_applicable_for_87_even_with_line_z():
    """Bus/transformer differential must not show km even if line Z1 exists."""
    from protection.models import ProtectionAssessment

    elec = _elec_from_currents(1000, 1000, 1000, i0=50)
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
            confidence="MEDIUM",
        )
    ]
    line = {
        "positive_sequence_impedance_ohm_per_km": {"R": 0.1, "X": 0.4},
        "length_km": 50.0,
    }
    r = classify_fault(elec, assessments=assessments, line_params=line)
    assert r.evidence.get("distance_applicable") is False
    assert r.distance["status"] == "NOT_APPLICABLE"
    assert r.distance.get("value_km") is None


def test_87l_with_line_z_distance_applicable():
    """Line differential + Z1: location in scope (typical 87L / 87L21 plants)."""
    from protection.models import ProtectionAssessment

    elec = _elec_from_currents(1000, 1000, 1000, i0=50)
    assessments = [
        ProtectionAssessment(
            element="87L",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            confidence="MEDIUM",
        )
    ]
    line = {
        "positive_sequence_impedance_ohm_per_km": {"R": 0.1, "X": 0.4},
        "length_km": 50.0,
    }
    r = classify_fault(elec, assessments=assessments, line_params=line)
    assert r.evidence.get("distance_applicable") is True


def test_87_with_21_backup_enabled_distance_applicable():
    """87 primary trip + 21 enabled as backup (may not have operated) → km in scope."""
    from protection.models import ProtectionAssessment

    elec = _elec_from_currents(800, 80, 80, i0=200)
    assessments = [
        ProtectionAssessment(
            element="87L",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            confidence="MEDIUM",
        ),
        ProtectionAssessment(
            element="21",
            enabled=True,
            pickup=False,
            trip=False,
            expected_operation="OPERATE",
            actual_operation="NOT_OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            confidence="MEDIUM",
        ),
    ]
    r = classify_fault(elec, assessments=assessments)
    assert r.evidence.get("distance_applicable") is True


def test_87b_with_21_backup_enabled_distance_applicable():
    """If distance backup is enabled alongside bus diff, location stays in scope."""
    from protection.models import ProtectionAssessment

    elec = _elec_from_currents(1000, 1000, 1000, i0=50)
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
            confidence="MEDIUM",
        ),
        ProtectionAssessment(
            element="21",
            enabled=True,
            pickup=False,
            trip=False,
            expected_operation="UNKNOWN",
            actual_operation="NOT_OPERATED",
            timing=None,
            consistency="UNVERIFIABLE",
            setting_reference={},
            confidence="LOW",
        ),
    ]
    r = classify_fault(elec, assessments=assessments)
    assert r.evidence.get("distance_applicable") is True


def test_oc_with_line_z_still_not_applicable():
    """Pure overcurrent + line Z1 must not unlock fault km."""
    from protection.models import ProtectionAssessment

    elec = _elec_from_currents(1000, 50, 50, i0=300)
    assessments = [
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
            confidence="MEDIUM",
        )
    ]
    line = {
        "positive_sequence_impedance_ohm_per_km": {"R": 0.1, "X": 0.4},
        "length_km": 20.0,
    }
    r = classify_fault(elec, assessments=assessments, line_params=line)
    assert r.evidence.get("distance_applicable") is False
    assert r.distance["status"] == "NOT_APPLICABLE"


def test_distance_not_calculable_when_21_operated_without_line_z():
    from protection.models import ProtectionAssessment

    elec = _elec_from_currents(1000, 50, 50, i0=300)
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
            confidence="MEDIUM",
        )
    ]
    r = classify_fault(elec, assessments=assessments)
    assert r.evidence.get("distance_applicable") is True
    assert r.distance["status"] == "NOT_CALCULABLE"
    assert r.distance.get("reason") and "NOT CALCULABLE" in r.distance["reason"]
