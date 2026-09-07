"""Harmonic analysis via DFT."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from common.results import ALGORITHM_VERSION, SignalResult, not_available, not_calculable


def compute_harmonics(
    samples: Sequence[float],
    *,
    sample_rate_hz: float,
    channel: str,
    nominal_frequency_hz: float = 50.0,
    max_harmonic: int = 15,
    timestamp: Optional[float] = None,
    unit: str = "",
    algorithm_version: str = ALGORITHM_VERSION,
) -> SignalResult:
    """
    Compute harmonic magnitudes (RMS) up to ``max_harmonic`` using integer-cycle DFT.
    """
    if samples is None or len(samples) == 0:
        return not_available(
            method="integer_cycle_dft_harmonics",
            unit=unit,
            input_channels=[channel],
            reason="No samples provided",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    if sample_rate_hz <= 0 or nominal_frequency_hz <= 0:
        return not_calculable(
            method="integer_cycle_dft_harmonics",
            unit=unit,
            input_channels=[channel],
            reason="Invalid sample rate or nominal frequency",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    arr = np.asarray(samples, dtype=float)
    spc = int(round(sample_rate_hz / nominal_frequency_hz))
    if spc < 4:
        return not_calculable(
            method="integer_cycle_dft_harmonics",
            unit=unit,
            input_channels=[channel],
            reason="Insufficient samples per cycle",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    n_cycles = len(arr) // spc
    if n_cycles < 1:
        return not_calculable(
            method="integer_cycle_dft_harmonics",
            unit=unit,
            input_channels=[channel],
            reason="Less than one fundamental cycle available",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    n = n_cycles * spc
    window = arr[-n:]
    if not np.all(np.isfinite(window)):
        return not_calculable(
            method="integer_cycle_dft_harmonics",
            unit=unit,
            input_channels=[channel],
            reason="Non-finite sample values present",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    # FFT and pick harmonic bins (bin = h * n_cycles)
    spectrum = np.fft.rfft(window)
    # Peak amplitude from rfft: 2/N * |X[k]| for k>0
    harmonics: dict[str, float] = {}
    for h in range(1, max_harmonic + 1):
        bin_idx = h * n_cycles
        if bin_idx >= len(spectrum):
            break
        peak = (2.0 / n) * abs(spectrum[bin_idx])
        harmonics[str(h)] = float(peak / np.sqrt(2.0))  # RMS

    fund = harmonics.get("1", 0.0)
    if fund > 1e-12:
        thd = float(
            np.sqrt(sum(v**2 for k, v in harmonics.items() if k != "1")) / fund * 100.0
        )
    else:
        thd = None

    return SignalResult(
        value={"harmonics_rms": harmonics, "thd_percent": thd},
        unit=unit,
        timestamp=timestamp,
        method="integer_cycle_dft_harmonics",
        algorithm_version=algorithm_version,
        input_channels=[channel],
        quality="GOOD" if thd is not None else "WARNING",
        status="OK" if thd is not None else "INCONCLUSIVE",
        reason=None if thd is not None else "Fundamental near zero; THD not calculable",
        metadata={"cycles": n_cycles, "max_harmonic": max_harmonic},
    )
