"""Timestamp normalization and integrity checks for COMTRADE records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence


@dataclass
class TimestampAssessment:
    """Result of timestamp integrity analysis."""

    normalized_us: list[int]
    is_monotonic: bool
    duplicate_count: int
    gap_count: int
    issues: list[str] = field(default_factory=list)
    expected_dt_us: Optional[float] = None
    time_multiplier_applied: float = 1.0


class TimestampEngine:
    """Normalize and assess COMTRADE sample timestamps.

    COMTRADE DAT timestamps are integer microsecond offsets from the first
    sample, optionally scaled by CFG ``timemult``. This engine:
    - applies ``timemult``
    - produces normalized µs-from-start integers
    - reports monotonicity / duplicate / gap issues
    - never silently repairs timestamps
    """

    def apply_multiplier(
        self, timestamps: Sequence[int | float], timemult: float = 1.0
    ) -> list[float]:
        """Apply CFG time stamp multiplication factor."""
        mult = float(timemult) if timemult not in (None, 0) else 1.0
        return [float(t) * mult for t in timestamps]

    def normalize_from_start(
        self, timestamps: Sequence[int | float], timemult: float = 1.0
    ) -> list[int]:
        """Return integer µs offsets relative to the first sample.

        If the first timestamp is non-zero, offsets are shifted so sample 0
        is at 0 µs. Fractional results after multiplier are rounded.
        """
        if not timestamps:
            return []
        scaled = self.apply_multiplier(timestamps, timemult)
        origin = scaled[0]
        return [int(round(t - origin)) for t in scaled]

    def assess(
        self,
        timestamps: Sequence[int | float],
        *,
        timemult: float = 1.0,
        sample_rate_hz: Optional[float] = None,
        tolerance_us: float = 1.0,
    ) -> TimestampAssessment:
        """Assess timestamp integrity without mutating inputs."""
        issues: list[str] = []
        mult = float(timemult) if timemult not in (None, 0) else 1.0
        if timemult in (None, 0):
            issues.append("timemult missing or zero; defaulted to 1.0 for assessment only")

        normalized = self.normalize_from_start(timestamps, mult)

        is_monotonic = True
        duplicate_count = 0
        for i in range(1, len(normalized)):
            if normalized[i] < normalized[i - 1]:
                is_monotonic = False
            elif normalized[i] == normalized[i - 1]:
                duplicate_count += 1

        if not is_monotonic:
            issues.append("timestamps are not strictly non-decreasing")
        if duplicate_count:
            issues.append(f"{duplicate_count} duplicate timestamp value(s)")

        expected_dt: Optional[float] = None
        gap_count = 0
        if sample_rate_hz and sample_rate_hz > 0:
            expected_dt = 1_000_000.0 / float(sample_rate_hz)
            for i in range(1, len(normalized)):
                dt = normalized[i] - normalized[i - 1]
                if abs(dt - expected_dt) > tolerance_us and dt > 0:
                    # Count only unexpectedly large gaps (> 1.5 * expected)
                    if dt > expected_dt * 1.5:
                        gap_count += 1
            if gap_count:
                issues.append(
                    f"{gap_count} inter-sample gap(s) exceed 1.5x expected dt "
                    f"({expected_dt:.3f} µs at {sample_rate_hz} Hz)"
                )

        return TimestampAssessment(
            normalized_us=normalized,
            is_monotonic=is_monotonic,
            duplicate_count=duplicate_count,
            gap_count=gap_count,
            issues=issues,
            expected_dt_us=expected_dt,
            time_multiplier_applied=mult,
        )

    def build_from_sample_rate(
        self, num_samples: int, sample_rate_hz: float
    ) -> list[int]:
        """Synthesize timestamps when DAT omits them (rare / non-compliant).

        Marked as synthesized — callers must record this as an unsupported /
        repaired situation; this method does not claim DAT fidelity.
        """
        if sample_rate_hz <= 0 or num_samples <= 0:
            return []
        dt = 1_000_000.0 / sample_rate_hz
        return [int(round(i * dt)) for i in range(num_samples)]
