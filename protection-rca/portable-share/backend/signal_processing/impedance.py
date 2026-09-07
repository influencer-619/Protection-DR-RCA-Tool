"""Apparent impedance from voltage and current phasors."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from common.results import ALGORITHM_VERSION, SignalResult, not_available, not_calculable
from signal_processing.phasor import compute_fundamental_phasor


def compute_apparent_impedance(
    voltage_samples: Sequence[float],
    current_samples: Sequence[float],
    *,
    sample_rate_hz: float,
    voltage_channel: str,
    current_channel: str,
    nominal_frequency_hz: float = 50.0,
    timestamp: Optional[float] = None,
    algorithm_version: str = ALGORITHM_VERSION,
) -> SignalResult:
    """Z = V / I (fundamental phasors). Returns R, X, |Z|, angle."""
    if voltage_samples is None or current_samples is None:
        return not_available(
            method="phasor_impedance",
            unit="ohm",
            input_channels=[voltage_channel, current_channel],
            reason="Voltage and current samples required",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    v_ph = compute_fundamental_phasor(
        voltage_samples,
        sample_rate_hz=sample_rate_hz,
        channel=voltage_channel,
        nominal_frequency_hz=nominal_frequency_hz,
        timestamp=timestamp,
        unit="V",
        algorithm_version=algorithm_version,
    )
    i_ph = compute_fundamental_phasor(
        current_samples,
        sample_rate_hz=sample_rate_hz,
        channel=current_channel,
        nominal_frequency_hz=nominal_frequency_hz,
        timestamp=timestamp,
        unit="A",
        algorithm_version=algorithm_version,
    )
    if v_ph.status != "OK" or i_ph.status != "OK":
        return not_calculable(
            method="phasor_impedance",
            unit="ohm",
            input_channels=[voltage_channel, current_channel],
            reason=f"Phasor failure: V={v_ph.reason}; I={i_ph.reason}",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    v = complex(v_ph.value["real"], v_ph.value["imag"])
    i = complex(i_ph.value["real"], i_ph.value["imag"])
    if abs(i) < 1e-9:
        return not_calculable(
            method="phasor_impedance",
            unit="ohm",
            input_channels=[voltage_channel, current_channel],
            reason="Current magnitude near zero; impedance not calculable",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    z = v / i
    return SignalResult(
        value={
            "R": float(z.real),
            "X": float(z.imag),
            "magnitude": float(np.abs(z)),
            "angle_deg": float(np.degrees(np.angle(z))),
        },
        unit="ohm",
        timestamp=timestamp,
        method="phasor_impedance",
        algorithm_version=algorithm_version,
        input_channels=[voltage_channel, current_channel],
        quality="GOOD",
        status="OK",
    )
