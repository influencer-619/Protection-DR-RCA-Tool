"""Quality assessment for parsed COMTRADE records."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.enums import DataQuality

from comtrade.canonical.model import CanonicalDisturbanceRecord
from comtrade.timestamps import TimestampAssessment, TimestampEngine


@dataclass
class QualityAssessment:
    """Aggregated data-quality view of a disturbance record."""

    overall: str
    score: float  # 0.0 – 1.0
    findings: list[dict[str, Any]] = field(default_factory=list)
    channel_quality: dict[str, str] = field(default_factory=dict)
    timestamp_assessment: Optional[TimestampAssessment] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "score": self.score,
            "findings": self.findings,
            "channel_quality": self.channel_quality,
            "timestamp": {
                "is_monotonic": self.timestamp_assessment.is_monotonic
                if self.timestamp_assessment
                else None,
                "duplicate_count": self.timestamp_assessment.duplicate_count
                if self.timestamp_assessment
                else None,
                "gap_count": self.timestamp_assessment.gap_count
                if self.timestamp_assessment
                else None,
                "issues": self.timestamp_assessment.issues
                if self.timestamp_assessment
                else [],
            },
        }


class QualityEngine:
    """Assess engineering quality of a :class:`CanonicalDisturbanceRecord`."""

    def __init__(self, timestamp_engine: Optional[TimestampEngine] = None) -> None:
        self._ts = timestamp_engine or TimestampEngine()

    def assess(self, record: CanonicalDisturbanceRecord) -> QualityAssessment:
        findings: list[dict[str, Any]] = []
        channel_quality: dict[str, str] = {}
        deductions = 0.0

        if record.samples <= 0:
            findings.append(
                {"severity": "error", "code": "NO_SAMPLES", "message": "Record has zero samples"}
            )
            deductions += 0.5

        if not record.analog_channels and not record.digital_channels:
            findings.append(
                {
                    "severity": "error",
                    "code": "NO_CHANNELS",
                    "message": "No analog or digital channels defined",
                }
            )
            deductions += 0.4

        # Timestamp integrity
        rate = (
            record.sample_rates[0].sample_rate_hz if record.sample_rates else None
        )
        ts_assessment = self._ts.assess(
            record.timestamps,
            timemult=1.0,  # already normalized in pipeline
            sample_rate_hz=rate,
        )
        for issue in ts_assessment.issues:
            findings.append(
                {"severity": "warning", "code": "TIMESTAMP", "message": issue}
            )
            deductions += 0.05

        if not ts_assessment.is_monotonic:
            deductions += 0.15

        # Per-channel missing / flat checks on scaled values
        for ch in record.analog_channels:
            series = record.scaled_values.get(ch.name) or record.raw_values.get(ch.name)
            if series is None:
                channel_quality[ch.name] = DataQuality.INVALID.value
                findings.append(
                    {
                        "severity": "error",
                        "code": "MISSING_SERIES",
                        "message": f"No data series for analog channel '{ch.name}'",
                        "channel": ch.name,
                    }
                )
                deductions += 0.1
                continue

            missing = sum(1 for v in series if v is None)
            missing_ratio = missing / len(series) if series else 1.0
            finite = [v for v in series if v is not None]

            if missing_ratio > 0.5:
                q = DataQuality.POOR.value
                deductions += 0.1
            elif missing_ratio > 0.05:
                q = DataQuality.WARNING.value
                deductions += 0.03
            elif len(set(round(v, 6) for v in finite)) <= 1 and finite:
                q = DataQuality.WARNING.value
                findings.append(
                    {
                        "severity": "warning",
                        "code": "FLAT_CHANNEL",
                        "message": f"Channel '{ch.name}' appears constant",
                        "channel": ch.name,
                    }
                )
                deductions += 0.02
            else:
                q = DataQuality.GOOD.value

            if missing:
                findings.append(
                    {
                        "severity": "info" if missing_ratio <= 0.05 else "warning",
                        "code": "MISSING_SAMPLES",
                        "message": f"{missing} missing sample(s) on '{ch.name}'",
                        "channel": ch.name,
                    }
                )
            channel_quality[ch.name] = q

        for ch in record.digital_channels:
            series = record.raw_values.get(ch.name)
            if series is None:
                channel_quality[ch.name] = DataQuality.INVALID.value
                deductions += 0.05
            else:
                channel_quality[ch.name] = DataQuality.GOOD.value

        if record.unsupported_features:
            for feat in record.unsupported_features:
                findings.append(
                    {
                        "severity": "warning",
                        "code": "UNSUPPORTED_FEATURE",
                        "message": feat,
                    }
                )
                deductions += 0.02

        score = max(0.0, min(1.0, 1.0 - deductions))
        if score >= 0.9 and not any(f["severity"] == "error" for f in findings):
            overall = DataQuality.GOOD.value
        elif score >= 0.75:
            overall = DataQuality.ACCEPTABLE.value
        elif score >= 0.5:
            overall = DataQuality.WARNING.value
        elif score >= 0.25:
            overall = DataQuality.POOR.value
        else:
            overall = DataQuality.INVALID.value

        return QualityAssessment(
            overall=overall,
            score=round(score, 4),
            findings=findings,
            channel_quality=channel_quality,
            timestamp_assessment=ts_assessment,
        )
