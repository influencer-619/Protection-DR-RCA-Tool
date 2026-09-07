"""Detect COMTRADE DAT encoding: ASCII / BINARY / BINARY32 / FLOAT32."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from comtrade._io import FilePath, read_bytes, sniff_text


@dataclass
class DataFormatDetection:
    data_format: str  # ASCII | BINARY | BINARY32 | FLOAT32 | UNKNOWN
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    source: str = "unknown"  # cfg_ft | dat_content | cff_marker


_FT_RE = re.compile(
    r"^\s*(ASCII|BINARY32|BINARY|FLOAT32)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


class ComtradeDataFormatDetector:
    """Detect DAT representation from CFG ``ft`` field and/or DAT/CFF content."""

    def detect_from_cfg(self, cfg_text: str) -> DataFormatDetection:
        evidence: list[str] = []
        for ln in cfg_text.splitlines():
            s = ln.strip()
            m = re.match(r"^(ASCII|BINARY32|BINARY|FLOAT32)$", s, re.I)
            if m:
                fmt = m.group(1).upper()
                evidence.append(f"CFG ft line: {fmt}")
                return DataFormatDetection(
                    data_format=fmt,
                    confidence=0.95,
                    evidence=evidence,
                    source="cfg_ft",
                )
        m = _FT_RE.search(cfg_text)
        if m:
            fmt = m.group(1).upper()
            evidence.append(f"CFG ft token: {fmt}")
            return DataFormatDetection(
                data_format=fmt,
                confidence=0.8,
                evidence=evidence,
                source="cfg_ft",
            )
        return DataFormatDetection(
            data_format="UNKNOWN",
            confidence=0.0,
            evidence=["no ft field found in CFG"],
        )

    def detect_from_dat(
        self,
        dat_path: FilePath,
        *,
        analog_count: int = 0,
        digital_count: int = 0,
        sample_hint: Optional[int] = None,
    ) -> DataFormatDetection:
        """Heuristic DAT content detection when CFG ft is missing."""
        data = read_bytes(dat_path, max_bytes=4096)
        evidence: list[str] = []

        text = sniff_text(data[:512])
        first = text.splitlines()[0] if text.splitlines() else ""
        if "," in first and re.match(r"^\s*\d+\s*,", first):
            evidence.append("DAT sample line is CSV with leading index")
            return DataFormatDetection(
                data_format="ASCII",
                confidence=0.85,
                evidence=evidence,
                source="dat_content",
            )

        if analog_count > 0:
            n_status_words = (digital_count + 15) // 16
            bin16 = 8 + 2 * analog_count + 2 * n_status_words
            bin32 = 8 + 4 * analog_count + 2 * n_status_words
            size = len(read_bytes(dat_path))
            evidence.append(f"DAT size={size}, bin16_rec={bin16}, bin32_rec={bin32}")
            if sample_hint and sample_hint > 0:
                if size == sample_hint * bin16:
                    return DataFormatDetection("BINARY", 0.7, evidence, "dat_content")
                if size == sample_hint * bin32:
                    evidence.append(
                        "size matches 32-bit analog; need CFG ft to disambiguate BINARY32/FLOAT32"
                    )
                    return DataFormatDetection("BINARY32", 0.5, evidence, "dat_content")
            return DataFormatDetection("BINARY", 0.4, evidence, "dat_content")

        evidence.append("opaque DAT; defaulting UNKNOWN")
        return DataFormatDetection("UNKNOWN", 0.1, evidence, "dat_content")

    def detect_from_cff(self, cff_text: str) -> DataFormatDetection:
        upper = cff_text.upper()
        evidence: list[str] = []
        for label, fmt in (
            ("DAT BINARY32", "BINARY32"),
            ("DAT FLOAT32", "FLOAT32"),
            ("DAT BINARY", "BINARY"),
            ("DAT ASCII", "ASCII"),
        ):
            if f"FILE TYPE: {label}" in upper or f"FILETYPE: {label}" in upper:
                evidence.append(f"CFF section: {label}")
                return DataFormatDetection(fmt, 0.95, evidence, "cff_marker")
        return self.detect_from_cfg(cff_text)

    def detect(
        self,
        *,
        cfg_text: Optional[str] = None,
        dat_path: Optional[FilePath] = None,
        cff_text: Optional[str] = None,
        analog_count: int = 0,
        digital_count: int = 0,
    ) -> DataFormatDetection:
        if cff_text:
            d = self.detect_from_cff(cff_text)
            if d.data_format != "UNKNOWN":
                return d
        if cfg_text:
            d = self.detect_from_cfg(cfg_text)
            if d.data_format != "UNKNOWN":
                return d
        if dat_path is not None:
            return self.detect_from_dat(
                dat_path, analog_count=analog_count, digital_count=digital_count
            )
        return DataFormatDetection(
            "UNKNOWN", 0.0, ["no inputs for data format detection"]
        )
