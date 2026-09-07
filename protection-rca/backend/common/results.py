"""Standard result envelopes for deterministic engineering calculations."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


ALGORITHM_VERSION = "1.0.0"


@dataclass
class SignalResult:
    """Every calculated engineering quantity carries provenance and quality."""

    value: Any
    unit: str
    timestamp: Optional[float]
    method: str
    algorithm_version: str
    input_channels: list[str]
    quality: str  # GOOD | ACCEPTABLE | WARNING | POOR | INVALID | NOT_AVAILABLE
    status: str = "OK"  # OK | NOT_AVAILABLE | NOT_CALCULABLE | INCONCLUSIVE
    reason: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def not_available(
    *,
    method: str,
    unit: str = "",
    input_channels: Optional[list[str]] = None,
    reason: str = "Required inputs unavailable",
    algorithm_version: str = ALGORITHM_VERSION,
    timestamp: Optional[float] = None,
) -> SignalResult:
    return SignalResult(
        value=None,
        unit=unit,
        timestamp=timestamp,
        method=method,
        algorithm_version=algorithm_version,
        input_channels=list(input_channels or []),
        quality="NOT_AVAILABLE",
        status="NOT_AVAILABLE",
        reason=reason,
    )


def not_calculable(
    *,
    method: str,
    unit: str = "",
    input_channels: Optional[list[str]] = None,
    reason: str = "Insufficient validated parameters",
    algorithm_version: str = ALGORITHM_VERSION,
    timestamp: Optional[float] = None,
) -> SignalResult:
    return SignalResult(
        value=None,
        unit=unit,
        timestamp=timestamp,
        method=method,
        algorithm_version=algorithm_version,
        input_channels=list(input_channels or []),
        quality="INVALID",
        status="NOT_CALCULABLE",
        reason=reason,
    )


def inconclusive(
    *,
    method: str,
    unit: str = "",
    input_channels: Optional[list[str]] = None,
    reason: str = "Evidence insufficient for definitive result",
    algorithm_version: str = ALGORITHM_VERSION,
    timestamp: Optional[float] = None,
    value: Any = None,
) -> SignalResult:
    return SignalResult(
        value=value,
        unit=unit,
        timestamp=timestamp,
        method=method,
        algorithm_version=algorithm_version,
        input_channels=list(input_channels or []),
        quality="WARNING",
        status="INCONCLUSIVE",
        reason=reason,
    )
