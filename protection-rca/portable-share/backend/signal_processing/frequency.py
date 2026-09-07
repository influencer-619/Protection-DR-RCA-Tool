"""Frequency estimation from zero-crossing / DFT phase."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from common.results import ALGORITHM_VERSION, SignalResult, not_available, not_calculable


def estimate_frequency(
    samples: Sequence[float],
    *,
    sample_rate_hz: float,
    channel: str,
    timestamp: Optional[float] = None,
    nominal_frequency_hz: float = 50.0,
    algorithm_version: str = ALGORITHM_VERSION,
) -> SignalResult:
    """Estimate frequency via interpolated zero-crossings over the provided window."""
    if samples is None or len(samples) < 8:
        return not_available(
            method="zero_crossing_interp",
            unit="Hz",
            input_channels=[channel],
            reason="Insufficient samples for frequency estimation",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    if sample_rate_hz <= 0:
        return not_calculable(
            method="zero_crossing_interp",
            unit="Hz",
            input_channels=[channel],
            reason="Invalid sample rate",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    arr = np.asarray(samples, dtype=float)
    if not np.all(np.isfinite(arr)):
        return not_calculable(
            method="zero_crossing_interp",
            unit="Hz",
            input_channels=[channel],
            reason="Non-finite sample values present",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    # Remove DC
    x = arr - np.mean(arr)
    crossings: list[float] = []
    for i in range(1, len(x)):
        if x[i - 1] <= 0.0 < x[i] or x[i - 1] >= 0.0 > x[i]:
            denom = x[i] - x[i - 1]
            if abs(denom) < 1e-15:
                continue
            frac = -x[i - 1] / denom
            crossings.append((i - 1 + frac) / sample_rate_hz)

    if len(crossings) < 3:
        return not_calculable(
            method="zero_crossing_interp",
            unit="Hz",
            input_channels=[channel],
            reason="Fewer than 3 zero-crossings detected",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    # Period between alternate crossings (full cycle)
    periods = []
    for i in range(2, len(crossings)):
        periods.append(crossings[i] - crossings[i - 2])
    periods_arr = np.asarray(periods, dtype=float)
    periods_arr = periods_arr[periods_arr > 0]
    if len(periods_arr) == 0:
        return not_calculable(
            method="zero_crossing_interp",
            unit="Hz",
            input_channels=[channel],
            reason="No valid periods from zero-crossings",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )

    freq = float(1.0 / np.median(periods_arr))
    # Sanity vs nominal
    quality = "GOOD"
    if abs(freq - nominal_frequency_hz) > 5.0:
        quality = "WARNING"
    return SignalResult(
        value=freq,
        unit="Hz",
        timestamp=timestamp,
        method="zero_crossing_interp",
        algorithm_version=algorithm_version,
        input_channels=[channel],
        quality=quality,
        status="OK",
        metadata={"zero_crossings": len(crossings), "periods_used": len(periods_arr)},
    )
