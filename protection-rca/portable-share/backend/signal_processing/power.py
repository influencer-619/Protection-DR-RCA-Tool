"""Active, reactive, apparent power and power factor."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from common.results import ALGORITHM_VERSION, SignalResult, not_available, not_calculable
from signal_processing.phasor import compute_fundamental_phasor


def compute_power(
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
    """Single-phase fundamental P, Q, S, and power factor from V/I phasors."""
    if voltage_samples is None or current_samples is None:
        return not_available(
            method="phasor_power",
            unit="VA",
            input_channels=[voltage_channel, current_channel],
            reason="Voltage and current samples required",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    if len(voltage_samples) == 0 or len(current_samples) == 0:
        return not_available(
            method="phasor_power",
            unit="VA",
            input_channels=[voltage_channel, current_channel],
            reason="Empty voltage or current samples",
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
            method="phasor_power",
            unit="VA",
            input_channels=[voltage_channel, current_channel],
            reason=f"Phasor failure: V={v_ph.reason}; I={i_ph.reason}",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    v = complex(v_ph.value["real"], v_ph.value["imag"])
    i = complex(i_ph.value["real"], i_ph.value["imag"])
    s_complex = v * np.conj(i)
    p = float(s_complex.real)
    q = float(s_complex.imag)
    s = float(np.abs(s_complex))
    if s < 1e-12:
        pf = None
        pf_status = "INCONCLUSIVE"
        reason = "Apparent power near zero; power factor not calculable"
    else:
        pf = float(p / s)
        pf_status = "OK"
        reason = None

    return SignalResult(
        value={"P": p, "Q": q, "S": s, "PF": pf, "pf_status": pf_status},
        unit="W/VAR/VA",
        timestamp=timestamp,
        method="phasor_power",
        algorithm_version=algorithm_version,
        input_channels=[voltage_channel, current_channel],
        quality="GOOD" if pf_status == "OK" else "WARNING",
        status="OK" if pf_status == "OK" else "INCONCLUSIVE",
        reason=reason,
    )
