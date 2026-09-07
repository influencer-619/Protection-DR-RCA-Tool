"""Base concrete parser wiring detection + CFG/DAT pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from comtrade.base import ComtradeParser, FileList
from comtrade.canonical.model import CanonicalDisturbanceRecord
from comtrade.detector.service import ComtradeDetectionService, DetectionResult
from comtrade.parsers._pipeline import RecordBuilder
from comtrade.parsers.cff.parser import CffParser
from comtrade.parsers.common import parse_cfg
from comtrade.validator import ComtradeValidator


class BaseComtradeParser(ComtradeParser):
    """Concrete parser shared by IEEE/IEC revision wrappers."""

    STANDARD: str = "IEEE"
    REVISION: str = "1999"

    def __init__(self) -> None:
        self.detector = ComtradeDetectionService()
        self.builder = RecordBuilder()
        self.cff_parser = CffParser()
        self.validator_engine = ComtradeValidator()

    def detect(self, files: FileList) -> dict:
        return self.detector.detect(files).to_dict()

    def parse(self, files: FileList) -> CanonicalDisturbanceRecord:
        detection = self.detector.detect(files)
        return self.parse_with_detection(files, detection)

    def parse_with_detection(
        self, files: FileList, detection: DetectionResult
    ) -> CanonicalDisturbanceRecord:
        standard = detection.standard if detection.standard != "UNKNOWN" else self.STANDARD
        revision = detection.revision if detection.revision != "UNKNOWN" else self.REVISION

        if detection.container == "CFF" and detection.cff_path:
            return self._parse_cff(Path(detection.cff_path), standard, revision)

        if detection.cfg_path and detection.dat_path:
            return self.builder.parse_cfg_dat_files(
                Path(detection.cfg_path),
                Path(detection.dat_path),
                standard=standard,
                revision=revision,
            )

        # Fallback: try to pair by extension from files list
        paths = [Path(f) for f in files]
        cfgs = [p for p in paths if p.suffix.lower() == ".cfg"]
        dats = [p for p in paths if p.suffix.lower() == ".dat"]
        cffs = [p for p in paths if p.suffix.lower() == ".cff"]
        if cffs:
            return self._parse_cff(cffs[0], standard, revision)
        if cfgs and dats:
            return self.builder.parse_cfg_dat_files(
                cfgs[0], dats[0], standard=standard, revision=revision
            )
        raise ValueError("unable to locate CFG+DAT or CFF inputs for parsing")

    def validate(self, record: CanonicalDisturbanceRecord) -> dict:
        return self.validator_engine.validate(record).to_dict()

    def _parse_cff(
        self, path: Path, standard: str, revision: str
    ) -> CanonicalDisturbanceRecord:
        sections = self.cff_parser.unpack(path)
        cfg = parse_cfg(sections.cfg_text)
        # Prefer section header format hint when CFG ft conflicts
        if sections.dat_format_hint and cfg.data_format != sections.dat_format_hint:
            cfg.warnings.append(
                f"CFF DAT section hint {sections.dat_format_hint} vs CFG ft {cfg.data_format}; "
                f"using section hint"
            )
            cfg.data_format = sections.dat_format_hint

        if cfg.data_format == "ASCII":
            dat = self.builder.parse_dat(cfg, dat_text=sections.dat_text or "")
        else:
            dat = self.builder.parse_dat(cfg, dat_bytes=sections.dat_binary or b"")

        extra = list(sections.warnings)
        return self.builder.build(
            cfg,
            dat,
            standard=standard,
            revision=revision,
            container="CFF",
            source_files=[str(path)],
            extra_unsupported=extra or None,
        )
