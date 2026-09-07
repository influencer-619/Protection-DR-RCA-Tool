"""Rate-of-change calculations (dI/dt, dV/dt)."""

from __future__ import annotations

from typing import Optional, Sequence

import numpy as np

from common.results import ALGORITHM_VERSION, SignalResult, not_available, not_calculable


def _derivative(
    samples: Sequence[float],
    *,
    sample_rate_hz: float,
    channel: str,
    method_name: str,
    unit: str,
    timestamp: Optional[float],
    algorithm_version: str,
) -> SignalResult:
    if samples is None or len(samples) < 2:
        return not_available(
            method=method_name,
            unit=unit,
            input_channels=[channel],
            reason="Need at least 2 samples",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    if sample_rate_hz <= 0:
        return not_calculable(
            method=method_name,
            unit=unit,
            input_channels=[channel],
            reason="Invalid sample rate",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    arr = np.asarray(samples, dtype=float)
    if not np.all(np.isfinite(arr)):
        return not_calculable(
            method=method_name,
            unit=unit,
            input_channels=[channel],
            reason="Non-finite sample values present",
            algorithm_version=algorithm_version,
            timestamp=timestamp,
        )
    dt = 1.0 / sample_rate_hz
    deriv = np.gradient(arr, dt)
    return SignalResult(
        value={
            "series": deriv.tolist(),
            "max_abs": float(np.max(np.abs(deriv))),
            "at_end": float(deriv[-1]),
        },
        unit=unit,
        timestamp=timestamp,
        method=method_name,
        algorithm_version=algorithm_version,
        input_channels=[channel],
        quality="GOOD",
        status="OK",
    )


def compute_di_dt(
    samples: Sequence[float],
    *,
    sample_rate_hz: float,
    channel: str,
    timestamp: Optional[float] = None,
    algorithm_version: str = ALGORITHM_VERSION,
) -> SignalResult:
    return _derivative(
        samples,
        sample_rate_hz=sample_rate_hz,
        channel=channel,
        method_name="numpy_gradient_di_dt",
        unit="A/s",
        timestamp=timestamp,
        algorithm_version=algorithm_version,
    )


def compute_dv_dt(
    samples: Sequence[float],
    *,
    sample_rate_hz: float,
    channel: str,
    timestamp: Optional[float] = None,
    algorithm_version: str = ALGORITHM_VERSION,
) -> SignalResult:
    return _derivative(
        samples,
        sample_rate_hz=sample_rate_hz,
        channel=channel,
        method_name="numpy_gradient_dv_dt",
        unit="V/s",
        timestamp=timestamp,
        algorithm_version=algorithm_version,
    )
