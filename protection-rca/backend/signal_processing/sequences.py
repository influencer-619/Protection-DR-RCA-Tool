"""Symmetrical component (sequence) calculations."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from common.results import ALGORITHM_VERSION, SignalResult, not_available, not_calculable
from signal_processing.phasor import compute_fundamental_phasor


def _phasor_to_complex(phasor_result: SignalResult) -> Optional[complex]:
    if phasor_result.status != "OK" or not isinstance(phasor_result.value, dict):
        return None
    return complex(phasor_result.value["real"], phasor_result.value["imag"])


def compute_sequence_components(
    phase_a: Any,
    phase_b: Any,
    phase_c: Any,
    *,
    sample_rate_hz: float,
    channels: list[str],
    nominal_frequency_hz: float = 50.0,
    timestamp: Optional[float] = None,
    unit: str = "",
    algorithm_version: str = ALGORITHM_VERSION,
) -> SignalResult:
    """
    Positive / negative / zero sequence from three-phase fundamental phasors.

    ``phase_a/b/c`` may be sample sequences or already-computed SignalResult phasors.
    """
    if any(p is None for p in (phase_a, phase_b, phase_c)):
        return not_available(
            method="fortescue_dft",
            unit=unit,
            input_channels=channels,
            reason="Three-phase inputs required",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    phasors = []
    for samples, ch in zip((phase_a, phase_b, phase_c), channels or ["A", "B", "C"]):
        if isinstance(samples, SignalResult):
            ph = samples
        else:
            ph = compute_fundamental_phasor(
                samples,
                sample_rate_hz=sample_rate_hz,
                channel=ch,
                nominal_frequency_hz=nominal_frequency_hz,
                timestamp=timestamp,
                unit=unit,
                algorithm_version=algorithm_version,
            )
        c = _phasor_to_complex(ph)
        if c is None:
            return not_calculable(
                method="fortescue_dft",
                unit=unit,
                input_channels=channels,
                reason=f"Phasor unavailable for channel {ch}: {ph.reason}",
                algorithm_version=algorithm_version,
                timestamp=timestamp,
            )
        phasors.append(c)

    a, b, c = phasors
    alpha = np.exp(1j * 2 * np.pi / 3)
    # Fortescue
    i0 = (a + b + c) / 3.0
    i1 = (a + alpha * b + alpha**2 * c) / 3.0
    i2 = (a + alpha**2 * b + alpha * c) / 3.0

    def _pack(z: complex) -> dict[str, float]:
        return {
            "magnitude": float(np.abs(z)),
            "angle_deg": float(np.degrees(np.angle(z))),
            "real": float(z.real),
            "imag": float(z.imag),
        }

    return SignalResult(
        value={
            "zero": _pack(i0),
            "positive": _pack(i1),
            "negative": _pack(i2),
        },
        unit=unit,
        timestamp=timestamp,
        method="fortescue_dft",
        algorithm_version=algorithm_version,
        input_channels=list(channels),
        quality="GOOD",
        status="OK",
    )
