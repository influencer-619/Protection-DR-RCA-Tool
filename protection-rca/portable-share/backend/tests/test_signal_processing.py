"""Unit tests for signal processing."""

from __future__ import annotations

import math

import numpy as np
import pytest

from signal_processing.frequency import estimate_frequency
from signal_processing.phasor import compute_fundamental_phasor
from signal_processing.power import compute_power
from signal_processing.rms import compute_peak, compute_rms
from signal_processing.sequences import compute_sequence_components
from signal_processing.impedance import compute_apparent_impedance
from signal_processing.harmonics import compute_harmonics
from signal_processing.derivatives import compute_di_dt


FS = 4000.0
F0 = 50.0
N = int(FS / F0) * 4  # 4 cycles


def _sine(amp: float, phase_deg: float = 0.0, freq: float = F0) -> np.ndarray:
    t = np.arange(N) / FS
    return amp * np.sqrt(2) * np.sin(2 * np.pi * freq * t + math.radians(phase_deg))


def test_rms_known_sine():
    x = _sine(100.0)
    r = compute_rms(x, sample_rate_hz=FS, channel="IA", unit="A", nominal_frequency_hz=F0)
    assert r.status == "OK"
    assert r.value == pytest.approx(100.0, rel=0.02)
    assert r.method == "true_rms"
    assert r.algorithm_version
    assert "IA" in r.input_channels


def test_rms_empty_not_available():
    r = compute_rms([], sample_rate_hz=FS, channel="IA")
    assert r.status == "NOT_AVAILABLE"
    assert r.value is None


def test_peak():
    x = _sine(10.0)
    r = compute_peak(x, channel="IA", unit="A")
    assert r.status == "OK"
    assert r.value == pytest.approx(10.0 * math.sqrt(2), rel=0.02)


def test_phasor_magnitude_and_angle():
    # Cosine reference: x = √2 A cos(ωt + φ)  → DFT angle ≈ φ
    t = np.arange(N) / FS
    x = 50.0 * np.sqrt(2) * np.cos(2 * np.pi * F0 * t + math.radians(30.0))
    r = compute_fundamental_phasor(
        x, sample_rate_hz=FS, channel="VA", nominal_frequency_hz=F0, unit="V"
    )
    assert r.status == "OK"
    assert r.value["magnitude"] == pytest.approx(50.0, rel=0.03)
    assert r.value["angle_deg"] == pytest.approx(30.0, abs=2.0)


def test_frequency_estimation():
    x = _sine(1.0, freq=50.0)
    r = estimate_frequency(x, sample_rate_hz=FS, channel="VA", nominal_frequency_hz=F0)
    assert r.status == "OK"
    assert r.value == pytest.approx(50.0, abs=0.5)


def test_sequences_balanced():
    a = _sine(100.0, 0)
    b = _sine(100.0, -120)
    c = _sine(100.0, 120)
    r = compute_sequence_components(
        a, b, c, sample_rate_hz=FS, channels=["IA", "IB", "IC"], nominal_frequency_hz=F0
    )
    assert r.status == "OK"
    assert r.value["positive"]["magnitude"] == pytest.approx(100.0, rel=0.05)
    assert r.value["negative"]["magnitude"] == pytest.approx(0.0, abs=5.0)
    assert r.value["zero"]["magnitude"] == pytest.approx(0.0, abs=5.0)


def test_power_and_impedance():
    v = _sine(110.0, 0)
    i = _sine(10.0, -30)
    p = compute_power(
        v, i, sample_rate_hz=FS, voltage_channel="VA", current_channel="IA", nominal_frequency_hz=F0
    )
    assert p.status in ("OK", "INCONCLUSIVE")
    assert p.value["S"] == pytest.approx(1100.0, rel=0.05)
    z = compute_apparent_impedance(
        v, i, sample_rate_hz=FS, voltage_channel="VA", current_channel="IA", nominal_frequency_hz=F0
    )
    assert z.status == "OK"
    assert z.value["magnitude"] == pytest.approx(11.0, rel=0.05)


def test_harmonics_and_di_dt():
    x = _sine(1.0) + 0.1 * _sine(1.0, freq=150.0)
    h = compute_harmonics(x, sample_rate_hz=FS, channel="IA", nominal_frequency_hz=F0)
    assert h.status in ("OK", "INCONCLUSIVE")
    d = compute_di_dt(x, sample_rate_hz=FS, channel="IA")
    assert d.status == "OK"
    assert "max_abs" in d.value


def test_impedance_zero_current_not_calculable():
    v = _sine(100.0)
    i = np.zeros(N)
    z = compute_apparent_impedance(
        v, i, sample_rate_hz=FS, voltage_channel="VA", current_channel="IA"
    )
    assert z.status == "NOT_CALCULABLE"
