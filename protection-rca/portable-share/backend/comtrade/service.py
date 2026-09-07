"""High-level COMTRADE detect → validate → parse service."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from comtrade.base import FileList
from comtrade.canonical.model import CanonicalDisturbanceRecord
from comtrade.detector.service import ComtradeDetectionService, DetectionResult
from comtrade.parsers.registry import ComtradeParserRegistry
from comtrade.validator import ComtradeValidator, ValidationResult


def _record_is_usable(record: CanonicalDisturbanceRecord) -> bool:
    """True when enough samples exist to drive waveforms / electrical analysis."""
    if record is None or int(getattr(record, "samples", 0) or 0) <= 0:
        return False
    scaled = record.scaled_values or {}
    raw = record.raw_values or {}
    for ch in record.analog_channels or []:
        name = getattr(ch, "name", None)
        if not name:
            continue
        series = scaled.get(name) or raw.get(name) or []
        if len(series) > 0:
            return True
    for ch in record.digital_channels or []:
        name = getattr(ch, "name", None)
        if not name:
            continue
        series = raw.get(name) or scaled.get(name) or []
        if len(series) > 0:
            return True
    return False


def _fatal_validation(validation: ValidationResult) -> bool:
    """Only truly unusable records are hard-failed."""
    fatal_codes = {"NO_SAMPLES", "NO_CHANNELS", "NULL_RECORD"}
    return any(
        i.severity == "error" and i.code in fatal_codes for i in (validation.issues or [])
    )


@dataclass
class ComtradeIngestResult:
    """Outcome of the full ingest pipeline."""

    detection: DetectionResult
    validation: Optional[ValidationResult] = None
    record: Optional[CanonicalDisturbanceRecord] = None
    success: bool = False
    error: Optional[str] = None
    stages: list[str] = field(default_factory=list)
    usable_with_warnings: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "error": self.error,
            "stages": self.stages,
            "usable_with_warnings": self.usable_with_warnings,
            "detection": self.detection.to_dict(),
            "validation": self.validation.to_dict() if self.validation else None,
            "record_id": self.record.record_id if self.record else None,
            "samples": self.record.samples if self.record else None,
            "station": self.record.station if self.record else None,
            "device": self.record.device if self.record else None,
        }


class ComtradeService:
    """Orchestrate detection, parsing, and validation for Protection RCA."""

    def __init__(self) -> None:
        self.detector = ComtradeDetectionService()
        self.registry = ComtradeParserRegistry()
        self.validator = ComtradeValidator()

    def detect(self, files: FileList) -> DetectionResult:
        return self.detector.detect(files)

    def validate(self, record: CanonicalDisturbanceRecord) -> ValidationResult:
        return self.validator.validate(record)

    def parse(self, files: FileList) -> CanonicalDisturbanceRecord:
        return self.registry.parse(files)

    def ingest(self, files: FileList, *, validate_after_parse: bool = True) -> ComtradeIngestResult:
        """Full pipeline: detect → parse → validate.

        Robust policy: if a record has usable samples, prefer soft-success even when
        detection was partial or validation reported non-fatal errors. Hard-fail only
        when there is no COMTRADE evidence or no usable channel data.
        """
        stages: list[str] = []
        detection = self.detect(files)
        stages.append("detect")

        if not detection.is_comtrade:
            return ComtradeIngestResult(
                detection=detection,
                success=False,
                error="not a COMTRADE record",
                stages=stages,
            )

        # Attempt parse even for PARTIALLY_SUPPORTED / recovered UNKNOWN fields.
        # Only skip when container is truly unknown and no CFG/DAT/CFF paths exist.
        if (
            detection.status == "UNSUPPORTED"
            and not detection.cfg_path
            and not detection.cff_path
        ):
            return ComtradeIngestResult(
                detection=detection,
                success=False,
                error=(
                    f"unsupported variant "
                    f"{detection.standard}/{detection.revision}/"
                    f"{detection.container}/{detection.data_format}"
                ),
                stages=stages,
            )

        try:
            record = self.registry.parse(files, detection=detection)
            stages.append("parse")
        except Exception as exc:
            # Last resort: try parse without relying on detection revision/format
            try:
                record = self.registry.parse(files, detection=None)
                stages.append("parse_fallback")
                detection.notes = list(detection.notes or []) + [
                    f"primary parse failed ({exc}); fallback parse used"
                ]
            except Exception as exc2:
                return ComtradeIngestResult(
                    detection=detection,
                    success=False,
                    error=f"parse failed: {exc2}",
                    stages=stages,
                )

        validation: Optional[ValidationResult] = None
        if validate_after_parse:
            validation = self.validate(record)
            stages.append("validate")
            if validation.status == "INVALID":
                if _record_is_usable(record) and not _fatal_validation(validation):
                    stages.append("soft_accept_invalid")
                    return ComtradeIngestResult(
                        detection=detection,
                        validation=validation,
                        record=record,
                        success=True,
                        usable_with_warnings=True,
                        error="validation INVALID but record usable — proceeding with warnings",
                        stages=stages,
                    )
                return ComtradeIngestResult(
                    detection=detection,
                    validation=validation,
                    record=record,
                    success=False,
                    error="validation status INVALID",
                    stages=stages,
                )

        return ComtradeIngestResult(
            detection=detection,
            validation=validation,
            record=record,
            success=True,
            usable_with_warnings=bool(
                validation and validation.status in ("VALID_WITH_WARNINGS", "PARTIALLY_SUPPORTED")
            ),
            stages=stages,
        )
