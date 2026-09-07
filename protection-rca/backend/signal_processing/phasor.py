"""Fundamental phasor estimation via full-cycle DFT (Goertzel-equivalent)."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from common.results import ALGORITHM_VERSION, SignalResult, not_available, not_calculable


def compute_fundamental_phasor(
    samples: Sequence[float],
    *,
    sample_rate_hz: float,
    channel: str,
    nominal_frequency_hz: float = 50.0,
    timestamp: Optional[float] = None,
    unit: str = "",
    algorithm_version: str = ALGORITHM_VERSION,
) -> SignalResult:
    """
    One-cycle DFT phasor at the fundamental frequency.

    Returns complex RMS phasor as ``{"magnitude": ..., "angle_deg": ..., "real": ..., "imag": ...}``.
    """
    if samples is None or len(samples) == 0:
        return not_available(
            method="full_cycle_dft",
            unit=unit,
            input_channels=[channel],
            reason="No samples provided",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    if sample_rate_hz <= 0 or nominal_frequency_hz <= 0:
        return not_calculable(
            method="full_cycle_dft",
            unit=unit,
            input_channels=[channel],
            reason="Invalid sample rate or nominal frequency",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    arr = np.asarray(samples, dtype=float)
    n = int(round(sample_rate_hz / nominal_frequency_hz))
    if n < 4:
        return not_calculable(
            method="full_cycle_dft",
            unit=unit,
            input_channels=[channel],
            reason="Insufficient samples per cycle for DFT",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    if len(arr) < n:
        return not_calculable(
            method="full_cycle_dft",
            unit=unit,
            input_channels=[channel],
            reason=f"Need at least {n} samples for one cycle; have {len(arr)}",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    if not np.all(np.isfinite(arr[-n:])):
        return not_calculable(
            method="full_cycle_dft",
            unit=unit,
            input_channels=[channel],
            reason="Non-finite sample values in analysis window",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    window = arr[-n:]
    # Goertzel / single-bin DFT at bin k=1 for one fundamental period
    k = 1
    n_idx = np.arange(n)
    twiddle = np.exp(-2j * np.pi * k * n_idx / n)
    # RMS phasor: (sqrt(2)/N) * sum  for peak-to-RMS of sine; use 2/N for peak, /sqrt(2) -> RMS
    c = (2.0 / n) * np.dot(window, twiddle)
    # Convert peak phasor to RMS
    rms_complex = c / np.sqrt(2.0)
    mag = float(np.abs(rms_complex))
    ang = float(np.degrees(np.angle(rms_complex)))
    return SignalResult(
        value={
            "magnitude": mag,
            "angle_deg": ang,
            "real": float(rms_complex.real),
            "imag": float(rms_complex.imag),
        },
        unit=unit,
        timestamp=timestamp,
        method="full_cycle_dft",
        algorithm_version=algorithm_version,
        input_channels=[channel],
        quality="GOOD",
        status="OK",
        metadata={"samples_per_cycle": n, "frequency_hz": nominal_frequency_hz},
    )
