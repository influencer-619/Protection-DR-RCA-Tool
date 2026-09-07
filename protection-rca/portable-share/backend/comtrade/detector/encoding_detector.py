"""Detect text encoding of COMTRADE CFG / ASCII DAT / CFF files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from comtrade._io import FilePath, read_bytes


@dataclass
class EncodingDetection:
    encoding: str  # utf-8 | utf-8-sig | latin-1 | ascii | unknown
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    bom: Optional[str] = None


class ComtradeEncodingDetector:
    """Detect character encoding from file bytes.

    IEEE C37.111-2013 permits UTF-8. Legacy files are typically ASCII / latin-1.
    """

    def detect(self, path: FilePath, max_bytes: int = 65536) -> EncodingDetection:
        data = read_bytes(path, max_bytes=max_bytes)
        return self.detect_bytes(data)

    def detect_bytes(self, data: bytes) -> EncodingDetection:
        evidence: list[str] = []
        bom: Optional[str] = None

        if data.startswith(b"\xef\xbb\xbf"):
            bom = "UTF-8"
            evidence.append("UTF-8 BOM present")
            try:
                data.decode("utf-8-sig")
                return EncodingDetection("utf-8-sig", 0.98, evidence, bom)
            except UnicodeDecodeError:
                evidence.append("BOM present but body not valid UTF-8")

        # Strict ASCII
        try:
            data.decode("ascii")
            evidence.append("pure ASCII")
            return EncodingDetection("ascii", 0.95, evidence, bom)
        except UnicodeDecodeError:
            pass

        try:
            data.decode("utf-8")
            evidence.append("valid UTF-8")
            return EncodingDetection("utf-8", 0.9, evidence, bom)
        except UnicodeDecodeError:
            evidence.append("not valid UTF-8")

        try:
            data.decode("latin-1")
            evidence.append("decodable as latin-1")
            return EncodingDetection("latin-1", 0.7, evidence, bom)
        except UnicodeDecodeError:
            pass

        return EncodingDetection("unknown", 0.0, evidence + ["undecodable"], bom)
