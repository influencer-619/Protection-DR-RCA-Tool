"""Tests for AFAS-style single-ended fault location."""

from __future__ import annotations

from common.results import SignalResult
from electrical_analysis.analyzer import ElectricalAnalysisResult
from fault_analysis.location import (
    compute_fault_locations,
    locate_reactance,
    locate_takagi,
    normalize_line_params,
)


def _sr(r: float, x: float) -> SignalResult:
    return SignalResult(
        value={"R": r, "X": x, "magnitude": (r * r + x * x) ** 0.5, "angle_deg": 0.0},
        unit="ohm",
        timestamp=None,
        method="test",
        algorithm_version="test",
        input_channels=[],
        quality="GOOD",
        status="OK",
    )


def _ph(mag: float, ang_deg: float = 0.0) -> SignalResult:
    import cmath
    import math

    z = cmath.rect(mag, math.radians(ang_deg))
    return SignalResult(
        value={
            "real": z.real,
            "imag": z.imag,
            "magnitude": mag,
            "angle_deg": ang_deg,
        },
        unit="A",
        timestamp=None,
        method="test",
        algorithm_version="test",
        input_channels=[],
        quality="GOOD",
        status="OK",
    )


def test_normalize_line_from_r_x():
    line = normalize_line_params(
        {
            "length_km": 20.0,
            "positive_sequence_r_ohm_per_km": 0.12,
            "positive_sequence_x_ohm_per_km": 0.40,
        }
    )
    z1 = line["positive_sequence_impedance_ohm_per_km"]
    assert isinstance(z1, complex)
    assert abs(z1.real - 0.12) < 1e-9
    assert abs(z1.imag - 0.40) < 1e-9


def test_reactance_ok():
    z1 = complex(0.12, 0.4)
    # 10 km worth of X
    row = locate_reactance(complex(1.2, 4.0), z1, 20.0)
    assert row["status"] == "OK"
    assert abs(row["distance_km"] - 10.0) < 1e-6


def test_reactance_missing_line():
    row = locate_reactance(complex(1, 1), None, None)
    assert row["status"] == "NOT_CALCULABLE"


def _elec() -> ElectricalAnalysisResult:
    return ElectricalAnalysisResult(
        record_id="test",
        nominal_frequency_hz=50.0,
        sample_rate_hz=1000.0,
    )


def test_takagi_not_for_abc():
    row = locate_takagi(_elec(), "ABC", complex(0.12, 0.4), 20.0)
    assert row["status"] == "NOT_CALCULABLE"


def test_compute_suite_with_impedance():
    elec = _elec()
    elec.impedance["phase_A"] = _sr(1.2, 4.0)
    elec.channel_roles = {"Ia": "IA", "Va": "VA", "Ib": "IB", "Ic": "IC"}
    elec.phasors = {
        "Va": _ph(1000, 0),
        "Ia": _ph(100, -80),
        "Ib": _ph(10, 120),
        "Ic": _ph(10, -120),
    }
    out = compute_fault_locations(
        elec,
        fault_type="AG",
        line_params={
            "length_km": 20,
            "positive_sequence_r_ohm_per_km": 0.12,
            "positive_sequence_x_ohm_per_km": 0.4,
        },
    )
    assert "algorithms" in out
    assert len(out["algorithms"]) == 3
    react = next(a for a in out["algorithms"] if "Reactance" in a["algorithm"])
    assert react["status"] == "OK"
    assert out["value_km"] is not None


def test_not_calculable_without_line():
    out = compute_fault_locations(_elec(), fault_type="AG", line_params=None)
    assert out["status"] == "NOT_CALCULABLE"
    assert out["value_km"] is None
    for a in out["algorithms"]:
        assert a["status"] in ("NOT_CALCULABLE", "INCONCLUSIVE")
