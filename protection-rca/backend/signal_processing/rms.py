"""RMS and peak calculations."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from common.results import ALGORITHM_VERSION, SignalResult, not_available, not_calculable


def compute_rms(
    samples: Sequence[float],
    *,
    sample_rate_hz: float,
    channel: str,
    timestamp: Optional[float] = None,
    unit: str = "",
    window_cycles: float = 1.0,
    nominal_frequency_hz: float = 50.0,
    algorithm_version: str = ALGORITHM_VERSION,
) -> SignalResult:
    """True RMS over a sliding window of ``window_cycles`` at nominal frequency."""
    if samples is None or len(samples) == 0:
        return not_available(
            method="true_rms",
            unit=unit,
            input_channels=[channel],
            reason="No samples provided",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    if sample_rate_hz <= 0 or nominal_frequency_hz <= 0:
        return not_calculable(
            method="true_rms",
            unit=unit,
            input_channels=[channel],
            reason="Invalid sample rate or nominal frequency",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    arr = np.asarray(samples, dtype=float)
    if not np.all(np.isfinite(arr)):
        return not_calculable(
            method="true_rms",
            unit=unit,
            input_channels=[channel],
            reason="Non-finite sample values present",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    window = max(1, int(round(window_cycles * sample_rate_hz / nominal_frequency_hz)))
    if len(arr) < window:
        # Use all available samples; flag quality
        window = len(arr)
        quality = "WARNING"
        meta = {"window_samples": window, "note": "window truncated to available samples"}
    else:
        quality = "GOOD"
        meta = {"window_samples": window}

    segment = arr[-window:]
    rms = float(np.sqrt(np.mean(segment**2)))
    return SignalResult(
        value=rms,
        unit=unit,
        timestamp=timestamp,
        method="true_rms",
        algorithm_version=algorithm_version,
        input_channels=[channel],
        quality=quality,
        status="OK",
        metadata=meta,
    )


def compute_peak(
    samples: Sequence[float],
    *,
    channel: str,
    timestamp: Optional[float] = None,
    unit: str = "",
    algorithm_version: str = ALGORITHM_VERSION,
) -> SignalResult:
    if samples is None or len(samples) == 0:
        return not_available(
            method="peak_absolute",
            unit=unit,
            input_channels=[channel],
            reason="No samples provided",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    arr = np.asarray(samples, dtype=float)
    if not np.all(np.isfinite(arr)):
        return not_calculable(
            method="peak_absolute",
            unit=unit,
            input_channels=[channel],
            reason="Non-finite sample values present",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    peak = float(np.max(np.abs(arr)))
    return SignalResult(
        value=peak,
        unit=unit,
        timestamp=timestamp,
        method="peak_absolute",
        algorithm_version=algorithm_version,
        input_channels=[channel],
        quality="GOOD",
        status="OK",
    )
