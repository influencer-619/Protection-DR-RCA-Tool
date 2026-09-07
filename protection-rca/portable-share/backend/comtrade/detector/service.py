"""Orchestrate COMTRADE detection into a single DetectionResult."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Sequence

from app.core.enums import SupportStatus

from comtrade._io import FilePath, read_text_lossy
from comtrade.detector.container_detector import ComtradeContainerDetector
from comtrade.detector.data_format_detector import ComtradeDataFormatDetector
from comtrade.detector.encoding_detector import ComtradeEncodingDetector
from comtrade.detector.format_detector import ComtradeFormatDetector
from comtrade.detector.timestamp_detector import ComtradeTimestampDetector
from comtrade.detector.version_detector import ComtradeVersionDetector


# Features we intentionally do not fully support yet
UNSUPPORTED_FEATURES = {
    "variable_sampling_nrates_gt_1": "Multiple sample-rate sections (nrates > 1) — partial",
    "cff_binary_embedded": "CFF with embedded binary DAT — supported via unpack",
    "utf16": "UTF-16 encoded CFG — unsupported",
}


@dataclass
class DetectionResult:
    standard: str
    revision: str
    container: str
    data_format: str
    confidence: float
    status: str  # SUPPORTED | PARTIALLY_SUPPORTED | UNSUPPORTED
    encoding: str = "utf-8"
    is_comtrade: bool = False
    cfg_path: Optional[str] = None
    dat_path: Optional[str] = None
    cff_path: Optional[str] = None
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    unsupported_features: list[str] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "standard": self.standard,
            "revision": self.revision,
            "container": self.container,
            "data_format": self.data_format,
            "confidence": self.confidence,
            "status": self.status,
            "encoding": self.encoding,
            "is_comtrade": self.is_comtrade,
            "cfg_path": self.cfg_path,
            "dat_path": self.dat_path,
            "cff_path": self.cff_path,
            "evidence": self.evidence,
            "notes": self.notes,
            "unsupported_features": self.unsupported_features,
            "details": self.details,
        }


class ComtradeDetectionService:
    """Run all detectors and produce a :class:`DetectionResult`."""

    def __init__(self) -> None:
        self.format_detector = ComtradeFormatDetector()
        self.version_detector = ComtradeVersionDetector()
        self.container_detector = ComtradeContainerDetector()
        self.data_format_detector = ComtradeDataFormatDetector()
        self.encoding_detector = ComtradeEncodingDetector()
        self.timestamp_detector = ComtradeTimestampDetector()

    def detect(self, files: Sequence[FilePath]) -> DetectionResult:
        if not files:
            return DetectionResult(
                standard="UNKNOWN",
                revision="UNKNOWN",
                container="UNKNOWN",
                data_format="UNKNOWN",
                confidence=0.0,
                status=SupportStatus.UNSUPPORTED.value,
                notes=["no files provided"],
            )

        fmt = self.format_detector.detect(files)
        container = self.container_detector.detect(files, format_hint=fmt)

        cfg_text: Optional[str] = None
        cff_text: Optional[str] = None
        encoding = "utf-8"
        evidence = list(fmt.evidence) + list(container.evidence)
        notes: list[str] = []
        unsupported: list[str] = []

        if container.container == "CFF" and container.cff_path:
            enc = self.encoding_detector.detect(container.cff_path)
            encoding = enc.encoding
            cff_text = read_text_lossy(container.cff_path)
            cfg_text = cff_text  # version/ft scanned from whole CFF
            evidence.extend(enc.evidence)
        elif container.cfg_path:
            enc = self.encoding_detector.detect(container.cfg_path)
            encoding = enc.encoding
            cfg_text = read_text_lossy(container.cfg_path)
            evidence.extend(enc.evidence)

        if not fmt.is_comtrade and container.container == "UNKNOWN":
            return DetectionResult(
                standard="UNKNOWN",
                revision="UNKNOWN",
                container="UNKNOWN",
                data_format="UNKNOWN",
                confidence=fmt.confidence,
                status=SupportStatus.UNSUPPORTED.value,
                encoding=encoding,
                is_comtrade=False,
                evidence=evidence,
                notes=["inputs do not appear to be COMTRADE"],
            )

        version = (
            self.version_detector.detect(cfg_text)
            if cfg_text
            else self.version_detector.detect("")
        )
        evidence.extend(version.evidence)
        notes.extend(version.notes)

        data_fmt = self.data_format_detector.detect(
            cfg_text=cfg_text,
            dat_path=container.dat_path,
            cff_text=cff_text,
        )
        evidence.extend(data_fmt.evidence)

        ts = self.timestamp_detector.detect(cfg_text or "")
        evidence.extend(ts.evidence)
        notes.extend(ts.notes)

        # nrates > 1 → partial
        if cfg_text:
            nrates = self._extract_nrates(cfg_text)
            if nrates is not None and nrates > 1:
                unsupported.append(UNSUPPORTED_FEATURES["variable_sampling_nrates_gt_1"])
                notes.append(f"nrates={nrates} (>1) — partial support")

        status = self._support_status(
            version.revision, container.container, data_fmt.data_format, unsupported
        )

        # Recover UNKNOWN fields so parse is still attempted for real CFG/DAT packs
        revision = version.revision
        data_format = data_fmt.data_format
        if revision == "UNKNOWN" and (container.cfg_path or container.cff_path):
            revision = "1999"
            notes.append("revision UNKNOWN — defaulting to IEEE 1999 for parse attempt")
            if status == SupportStatus.UNSUPPORTED.value:
                status = SupportStatus.PARTIALLY_SUPPORTED.value
        if data_format == "UNKNOWN" and (container.cfg_path or container.dat_path or container.cff_path):
            # Prefer DAT sniff; else ASCII (most disturbance records)
            recovered = "ASCII"
            if container.dat_path:
                try:
                    sniffed = self.data_format_detector.detect_from_dat(container.dat_path)
                    if sniffed.data_format.upper() in ("ASCII", "BINARY", "BINARY32", "FLOAT32"):
                        recovered = sniffed.data_format.upper()
                except Exception:
                    pass
            data_format = recovered
            notes.append(f"data_format UNKNOWN — recovered as {data_format}")
            if status == SupportStatus.UNSUPPORTED.value:
                status = SupportStatus.PARTIALLY_SUPPORTED.value
        if container.container == "UNKNOWN" and (container.cfg_path and container.dat_path):
            notes.append("container recovered as CFG_DAT")
            # container field on result uses container.container — fix below
            status = SupportStatus.PARTIALLY_SUPPORTED.value

        confidence = min(
            1.0,
            (
                fmt.confidence * 0.25
                + version.confidence * 0.25
                + container.confidence * 0.25
                + data_fmt.confidence * 0.25
            ),
        )

        cont_name = container.container
        if cont_name == "UNKNOWN" and container.cfg_path and container.dat_path:
            cont_name = "CFG_DAT"

        return DetectionResult(
            standard=version.standard if version.standard != "UNKNOWN" else "IEEE",
            revision=revision,
            container=cont_name,
            data_format=data_format,
            confidence=round(confidence, 4),
            status=status,
            encoding=encoding,
            is_comtrade=True,
            cfg_path=str(container.cfg_path) if container.cfg_path else None,
            dat_path=str(container.dat_path) if container.dat_path else None,
            cff_path=str(container.cff_path) if container.cff_path else None,
            evidence=evidence,
            notes=notes,
            unsupported_features=unsupported,
            details={
                "timestamp": {
                    "has_start_time": ts.has_start_time,
                    "has_trigger_time": ts.has_trigger_time,
                    "date_format": ts.date_format,
                    "time_multiplier": ts.time_multiplier,
                    "has_2013_time_fields": ts.has_2013_time_fields,
                },
                "data_format_source": data_fmt.source,
            },
        )

    @staticmethod
    def _extract_nrates(cfg_text: str) -> Optional[int]:
        lines = [ln.strip() for ln in cfg_text.splitlines() if ln.strip()]
        # After channel defs and frequency, nrates is a single integer line
        # Heuristic: find a lone integer after a float frequency line
        for i, ln in enumerate(lines):
            try:
                freq = float(ln.split(",")[0])
            except ValueError:
                continue
            if 15.0 <= freq <= 70.0 and i + 1 < len(lines):
                try:
                    return int(lines[i + 1].split(",")[0])
                except ValueError:
                    return None
        return None

    @staticmethod
    def _support_status(
        revision: str, container: str, data_format: str, unsupported: list[str]
    ) -> str:
        if revision == "UNKNOWN" or container == "UNKNOWN" or data_format == "UNKNOWN":
            return SupportStatus.UNSUPPORTED.value

        supported_revisions = {"1991", "1999", "2001", "2013"}
        supported_formats = {"ASCII", "BINARY", "BINARY32", "FLOAT32"}
        supported_containers = {"CFG_DAT", "CFF"}

        if (
            revision not in supported_revisions
            or data_format not in supported_formats
            or container not in supported_containers
        ):
            return SupportStatus.UNSUPPORTED.value

        if unsupported:
            return SupportStatus.PARTIALLY_SUPPORTED.value

        # 1991 is supported with reduced channel-field fidelity
        if revision == "1991":
            return SupportStatus.PARTIALLY_SUPPORTED.value

        return SupportStatus.SUPPORTED.value
