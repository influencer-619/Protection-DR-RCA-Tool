"""Apparent impedance from voltage and current phasors."""

from __future__ import annotations

from typing import Any, Optional, Sequence

import numpy as np

from common.results import ALGORITHM_VERSION, SignalResult, not_available, not_calculable
from signal_processing.phasor import compute_fundamental_phasor


def _z_from_complex(
    z: complex,
    *,
    input_channels: list[str],
    method: str,
    timestamp: Optional[float],
    algorithm_version: str,
    metadata: Optional[dict[str, Any]] = None,
) -> SignalResult:
    return SignalResult(
        value={
            "R": float(z.real),
            "X": float(z.imag),
            "magnitude": float(np.abs(z)),
            "angle_deg": float(np.degrees(np.angle(z))),
        },
        unit="Ω",
        timestamp=timestamp,
        method=method,
        algorithm_version=algorithm_version,
        input_channels=input_channels,
        quality="GOOD",
        status="OK",
        metadata=metadata or {},
    )


def compute_apparent_impedance(
    voltage_samples: Sequence[float],
    current_samples: Sequence[float],
    *,
    sample_rate_hz: float,
    voltage_channel: str,
    current_channel: str,
    nominal_frequency_hz: float = 50.0,
    timestamp: Optional[float] = None,
    voltage_unit: str = "V",
    current_unit: str = "A",
    algorithm_version: str = ALGORITHM_VERSION,
) -> SignalResult:
    """Z = V / I (fundamental phasors). Returns R, X, |Z|, angle in ohms.

    Scales kV→V and kA→A so Z stays in Ω regardless of COMTRADE uu.
    """
    from common.units import normalize_unit, to_si_current_scale, to_si_voltage_scale

    if voltage_samples is None or current_samples is None:
        return not_available(
            method="phasor_impedance",
            unit="Ω",
            input_channels=[voltage_channel, current_channel],
            reason="Voltage and current samples required",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    v_unit = normalize_unit(voltage_unit, role="V") or "V"
    i_unit = normalize_unit(current_unit, role="I") or "A"

    v_ph = compute_fundamental_phasor(
        voltage_samples,
        sample_rate_hz=sample_rate_hz,
        channel=voltage_channel,
        nominal_frequency_hz=nominal_frequency_hz,
        timestamp=timestamp,
        unit=v_unit,
        algorithm_version=algorithm_version,
    )
    i_ph = compute_fundamental_phasor(
        current_samples,
        sample_rate_hz=sample_rate_hz,
        channel=current_channel,
        nominal_frequency_hz=nominal_frequency_hz,
        timestamp=timestamp,
        unit=i_unit,
        algorithm_version=algorithm_version,
    )
    if v_ph.status != "OK" or i_ph.status != "OK":
        return not_calculable(
            method="phasor_impedance",
            unit="Ω",
            input_channels=[voltage_channel, current_channel],
            reason=f"Phasor failure: V={v_ph.reason}; I={i_ph.reason}",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    v = complex(v_ph.value["real"], v_ph.value["imag"]) * to_si_voltage_scale(v_unit)
    i = complex(i_ph.value["real"], i_ph.value["imag"]) * to_si_current_scale(i_unit)
    if abs(i) < 1e-9:
        return not_calculable(
            method="phasor_impedance",
            unit="Ω",
            input_channels=[voltage_channel, current_channel],
            reason="Current magnitude near zero; impedance not calculable",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    z = v / i
    return _z_from_complex(
        z,
        input_channels=[voltage_channel, current_channel],
        method="phasor_impedance",
        timestamp=timestamp,
        algorithm_version=algorithm_version,
        metadata={"voltage_unit": v_unit, "current_unit": i_unit, "loop": "phase"},
    )


def compute_delta_loop_impedance(
    v1_samples: Sequence[float],
    i1_samples: Sequence[float],
    v2_samples: Sequence[float],
    i2_samples: Sequence[float],
    *,
    sample_rate_hz: float,
    channels: Sequence[str],
    nominal_frequency_hz: float = 50.0,
    timestamp: Optional[float] = None,
    voltage_unit: str = "V",
    current_unit: str = "A",
    loop_label: str = "AB",
    algorithm_version: str = ALGORITHM_VERSION,
) -> SignalResult:
    """Phase-phase loop Z = (V1−V2) / (I1−I2) — primary R–X quantity for AB/BC/CA/ABG/…"""
    from common.units import normalize_unit, to_si_current_scale, to_si_voltage_scale

    ch = list(channels)
    if any(s is None for s in (v1_samples, i1_samples, v2_samples, i2_samples)):
        return not_available(
            method="delta_loop_impedance",
            unit="Ω",
            input_channels=ch,
            reason="Both phase V/I samples required for delta loop",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    v_unit = normalize_unit(voltage_unit, role="V") or "V"
    i_unit = normalize_unit(current_unit, role="I") or "A"
    vs = to_si_voltage_scale(v_unit)
    isc = to_si_current_scale(i_unit)

    phasors = []
    for samples, ch_name, role_unit, scale in (
        (v1_samples, ch[0] if len(ch) > 0 else "V1", v_unit, vs),
        (i1_samples, ch[1] if len(ch) > 1 else "I1", i_unit, isc),
        (v2_samples, ch[2] if len(ch) > 2 else "V2", v_unit, vs),
        (i2_samples, ch[3] if len(ch) > 3 else "I2", i_unit, isc),
    ):
        ph = compute_fundamental_phasor(
            samples,
            sample_rate_hz=sample_rate_hz,
            channel=ch_name,
            nominal_frequency_hz=nominal_frequency_hz,
            timestamp=timestamp,
            unit=role_unit,
            algorithm_version=algorithm_version,
        )
        if ph.status != "OK" or not isinstance(ph.value, dict):
            return not_calculable(
                method="delta_loop_impedance",
                unit="Ω",
                input_channels=ch,
                reason=f"Phasor failure on {ch_name}: {ph.reason}",
                algorithm_version=algorithm_version,
                timestamp=timestamp,
            )
        phasors.append(complex(ph.value["real"], ph.value["imag"]) * scale)

    v1, i1, v2, i2 = phasors
    di = i1 - i2
    if abs(di) < 1e-9:
        return not_calculable(
            method="delta_loop_impedance",
            unit="Ω",
            input_channels=ch,
            reason="Delta current near zero; loop impedance not calculable",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    z = (v1 - v2) / di
    return _z_from_complex(
        z,
        input_channels=ch,
        method="delta_loop_impedance",
        timestamp=timestamp,
        algorithm_version=algorithm_version,
        metadata={
            "voltage_unit": v_unit,
            "current_unit": i_unit,
            "loop": loop_label,
            "formula": "(V1-V2)/(I1-I2)",
        },
    )
