"""Parser registry — select concrete parser from detection result."""

from __future__ import annotations

from typing import Optional, Sequence, Type

from comtrade.base import ComtradeParser, FileList
from comtrade.canonical.model import CanonicalDisturbanceRecord
from comtrade.detector.service import ComtradeDetectionService, DetectionResult
from comtrade.parsers.iec_2001.parser import Iec2001Parser
from comtrade.parsers.iec_2013.parser import Iec2013Parser
from comtrade.parsers.ieee_1991.parser import Ieee1991Parser
from comtrade.parsers.ieee_1999.parser import Ieee1999Parser
from comtrade.parsers.ieee_2013.parser import Ieee2013Parser


class ComtradeParserRegistry:
    """Map (standard, revision) → parser class and dispatch parse/detect."""

    def __init__(self) -> None:
        self.detector = ComtradeDetectionService()
        self._registry: dict[tuple[str, str], Type[ComtradeParser]] = {
            ("IEEE", "1991"): Ieee1991Parser,
            ("IEEE", "1999"): Ieee1999Parser,
            ("IEEE", "2013"): Ieee2013Parser,
            ("IEC", "2001"): Iec2001Parser,
            ("IEC", "2013"): Iec2013Parser,
            # dual-logo aliases
            ("IEC", "1999"): Iec2001Parser,
            ("IEEE", "2001"): Ieee1999Parser,
        }

    def select(self, detection: DetectionResult) -> ComtradeParser:
        key = (detection.standard.upper(), detection.revision)
        cls = self._registry.get(key)
        if cls is None:
            # Fallbacks by revision alone
            if detection.revision == "2013":
                cls = Ieee2013Parser if detection.standard.upper() != "IEC" else Iec2013Parser
            elif detection.revision in ("1999", "2001"):
                cls = Ieee1999Parser if detection.standard.upper() != "IEC" else Iec2001Parser
            elif detection.revision == "1991":
                cls = Ieee1991Parser
            else:
                # Default to 1999 as most common legacy format
                cls = Ieee1999Parser
        return cls()

    def detect(self, files: FileList) -> DetectionResult:
        return self.detector.detect(files)

    def parse(self, files: FileList, detection: Optional[DetectionResult] = None) -> CanonicalDisturbanceRecord:
        detection = detection or self.detect(files)
        if not detection.is_comtrade:
            raise ValueError("inputs are not a recognized COMTRADE record")
        if detection.status == "UNSUPPORTED":
            raise ValueError(
                f"unsupported COMTRADE variant: "
                f"{detection.standard}/{detection.revision}/{detection.data_format}"
            )
        parser = self.select(detection)
        if hasattr(parser, "parse_with_detection"):
            return parser.parse_with_detection(files, detection)  # type: ignore[attr-defined]
        return parser.parse(files)

    def available(self) -> list[dict[str, str]]:
        seen: set[tuple[str, str]] = set()
        out: list[dict[str, str]] = []
        for (std, rev), cls in self._registry.items():
            if (std, rev) in seen:
                continue
            seen.add((std, rev))
            out.append({"standard": std, "revision": rev, "parser": cls.__name__})
        return out
