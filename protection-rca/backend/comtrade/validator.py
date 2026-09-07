"""COMTRADE record validation — never silently repairs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from app.core.enums import ValidationStatus

from comtrade.canonical.model import CanonicalDisturbanceRecord
from comtrade.timestamps import TimestampEngine


@dataclass
class ValidationIssue:
    severity: str  # error | warning | info
    code: str
    message: str
    field: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        d = {"severity": self.severity, "code": self.code, "message": self.message}
        if self.field:
            d["field"] = self.field
        return d


@dataclass
class ValidationResult:
    status: str
    issues: list[ValidationIssue] = field(default_factory=list)
    checks_passed: int = 0
    checks_failed: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "issues": [i.to_dict() for i in self.issues],
            "checks_passed": self.checks_passed,
            "checks_failed": self.checks_failed,
        }


class ComtradeValidator:
    """Comprehensive structural / consistency validation of a parsed record.

    Status vocabulary (from ``ValidationStatus``):
      VALID, VALID_WITH_WARNINGS, PARTIALLY_SUPPORTED, NOT_VALIDATED, INVALID

    This validator never mutates or repairs the record.
    """

    def __init__(self, timestamp_engine: Optional[TimestampEngine] = None) -> None:
        self._ts = timestamp_engine or TimestampEngine()

    def validate(self, record: CanonicalDisturbanceRecord) -> ValidationResult:
        if record is None:
            return ValidationResult(
                status=ValidationStatus.NOT_VALIDATED.value,
                issues=[
                    ValidationIssue("error", "NULL_RECORD", "Record is None")
                ],
                checks_failed=1,
            )

        issues: list[ValidationIssue] = []
        passed = 0
        failed = 0

        def ok() -> None:
            nonlocal passed
            passed += 1

        def fail(sev: str, code: str, msg: str, field: Optional[str] = None) -> None:
            nonlocal failed
            failed += 1
            issues.append(ValidationIssue(sev, code, msg, field))

        # --- Identity / metadata ---
        if not record.record_id:
            fail("error", "NO_RECORD_ID", "record_id is empty")
        else:
            ok()

        if record.standard not in ("IEEE", "IEC"):
            fail("warning", "UNKNOWN_STANDARD", f"standard={record.standard}")
        else:
            ok()

        if record.revision not in ("1991", "1999", "2001", "2013"):
            fail("error", "UNKNOWN_REVISION", f"revision={record.revision}")
        else:
            ok()

        if record.container not in ("CFG_DAT", "CFF"):
            fail("error", "UNKNOWN_CONTAINER", f"container={record.container}")
        else:
            ok()

        # --- Channels ---
        n_a = len(record.analog_channels)
        n_d = len(record.digital_channels)
        if n_a == 0 and n_d == 0:
            fail("error", "NO_CHANNELS", "no analog or digital channels")
        else:
            ok()

        names = [c.name for c in record.analog_channels] + [
            c.name for c in record.digital_channels
        ]
        if len(names) != len(set(names)):
            fail("warning", "DUPLICATE_CHANNEL_NAMES", "duplicate channel names present")
        else:
            ok()

        for ch in record.analog_channels:
            if ch.a == 0 and ch.b == 0:
                fail(
                    "warning",
                    "ZERO_SCALE",
                    f"analog '{ch.name}' has a=0 and b=0",
                    ch.name,
                )
            if ch.primary is not None and ch.secondary is not None:
                if abs(ch.secondary) < 1e-15:
                    fail(
                        "warning",
                        "ZERO_SECONDARY",
                        f"analog '{ch.name}' secondary is zero — PS scaling skipped",
                        ch.name,
                    )

        # --- Samples ---
        if record.samples <= 0:
            fail("error", "NO_SAMPLES", "sample count is zero")
        else:
            ok()

        if record.timestamps and len(record.timestamps) != record.samples:
            fail(
                "warning",
                "TIMESTAMP_LENGTH",
                f"timestamps ({len(record.timestamps)}) != samples ({record.samples})",
            )
        elif record.timestamps:
            ok()

        for ch in record.analog_channels:
            series = record.raw_values.get(ch.name)
            if series is None:
                fail("warning", "MISSING_RAW", f"missing raw series for '{ch.name}'", ch.name)
            elif len(series) != record.samples:
                fail(
                    "warning",
                    "RAW_LENGTH",
                    f"raw '{ch.name}' length {len(series)} != samples {record.samples}",
                    ch.name,
                )
            else:
                ok()

            scaled = record.scaled_values.get(ch.name)
            if scaled is None:
                fail(
                    "warning",
                    "MISSING_SCALED",
                    f"missing scaled series for '{ch.name}'",
                    ch.name,
                )
            elif len(scaled) != record.samples:
                fail(
                    "warning",
                    "SCALED_LENGTH",
                    f"scaled '{ch.name}' length mismatch",
                    ch.name,
                )
            else:
                ok()

        for ch in record.digital_channels:
            series = record.raw_values.get(ch.name)
            if series is None:
                fail("warning", "MISSING_DIGITAL", f"missing digital '{ch.name}'", ch.name)
            elif len(series) != record.samples:
                fail(
                    "warning",
                    "DIGITAL_LENGTH",
                    f"digital '{ch.name}' length mismatch",
                    ch.name,
                )
            else:
                ok()

        # --- Sample rates ---
        if not record.sample_rates:
            fail("warning", "NO_SAMPLE_RATE", "no sample rate sections")
        else:
            ok()
            if len(record.sample_rates) > 1:
                fail(
                    "warning",
                    "MULTI_RATE",
                    "nrates > 1 — partially supported",
                )
            for i, sec in enumerate(record.sample_rates):
                if sec.sample_rate_hz <= 0:
                    fail(
                        "warning",
                        "BAD_SAMPLE_RATE",
                        f"sample_rates[{i}].sample_rate_hz <= 0 — may recover from timestamps",
                    )

        # --- Times ---
        if record.start_time is None:
            fail("warning", "NO_START_TIME", "start_time missing")
        else:
            ok()
        if record.trigger_time is None:
            fail("warning", "NO_TRIGGER_TIME", "trigger_time missing")
        else:
            ok()
            if record.start_time and record.trigger_time < record.start_time:
                fail(
                    "warning",
                    "TRIGGER_BEFORE_START",
                    "trigger_time is before start_time",
                )

        # --- Timestamps integrity (report only) ---
        if record.timestamps:
            rate = (
                record.sample_rates[0].sample_rate_hz if record.sample_rates else None
            )
            assessment = self._ts.assess(
                record.timestamps, timemult=1.0, sample_rate_hz=rate
            )
            if not assessment.is_monotonic:
                fail("warning", "NON_MONOTONIC", "timestamps are not monotonic")
            else:
                ok()
            if assessment.duplicate_count:
                fail(
                    "warning",
                    "DUPLICATE_TIMESTAMPS",
                    f"{assessment.duplicate_count} duplicate timestamp(s)",
                )

        # --- Frequency ---
        if not (15.0 <= record.nominal_frequency <= 70.0):
            fail(
                "warning",
                "ODD_FREQUENCY",
                f"nominal_frequency={record.nominal_frequency} outside 15–70 Hz",
            )
        else:
            ok()

        # --- Source files ---
        if not record.source_files:
            fail("warning", "NO_SOURCE_FILES", "source_files empty")
        else:
            ok()

        # --- Unsupported features ---
        if record.unsupported_features:
            for feat in record.unsupported_features:
                issues.append(
                    ValidationIssue("warning", "UNSUPPORTED_FEATURE", feat)
                )

        # --- Status decision ---
        has_error = any(i.severity == "error" for i in issues)
        has_warning = any(i.severity == "warning" for i in issues)
        has_partial = any(i.code in ("MULTI_RATE", "UNSUPPORTED_FEATURE") for i in issues)

        if has_error:
            status = ValidationStatus.INVALID.value
        elif has_partial and record.revision == "1991":
            status = ValidationStatus.PARTIALLY_SUPPORTED.value
        elif has_partial:
            status = ValidationStatus.PARTIALLY_SUPPORTED.value
        elif has_warning:
            status = ValidationStatus.VALID_WITH_WARNINGS.value
        else:
            status = ValidationStatus.VALID.value

        return ValidationResult(
            status=status,
            issues=issues,
            checks_passed=passed,
            checks_failed=failed,
        )
