"""Detect timestamp conventions in COMTRADE CFG/DAT."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TimestampDetection:
    has_start_time: bool = False
    has_trigger_time: bool = False
    date_format: str = "UNKNOWN"  # DD/MM/YYYY | MM/DD/YYYY | UNKNOWN
    time_multiplier: Optional[float] = None
    has_2013_time_fields: bool = False
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


_DATE_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{2,4}),\s*(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?"
)


class ComtradeTimestampDetector:
    """Inspect CFG date/time lines and timemult."""

    def detect(self, cfg_text: str) -> TimestampDetection:
        lines = [ln.strip() for ln in cfg_text.splitlines() if ln.strip()]
        evidence: list[str] = []
        notes: list[str] = []
        date_lines: list[str] = []
        timemult: Optional[float] = None
        has_2013 = False

        # Locate ft line, then start/trigger are the two preceding date lines
        ft_idx = None
        for i, ln in enumerate(lines):
            if re.match(r"^(ASCII|BINARY32|BINARY|FLOAT32)$", ln, re.I):
                ft_idx = i
                break

        if ft_idx is not None and ft_idx >= 2:
            cand = [lines[ft_idx - 2], lines[ft_idx - 1]]
            for c in cand:
                if _DATE_RE.match(c.split(",")[0] + "," + ",".join(c.split(",")[1:])) or _DATE_RE.match(
                    c
                ):
                    date_lines.append(c)
            # timemult is typically the line after ft
            if ft_idx + 1 < len(lines):
                try:
                    timemult = float(lines[ft_idx + 1].split(",")[0].strip())
                    evidence.append(f"timemult={timemult}")
                except ValueError:
                    notes.append("timemult line not numeric")
            # 2013 trailers
            if ft_idx + 3 < len(lines):
                has_2013 = True
                evidence.append("post-timemult trailer lines present (likely 2013)")
        else:
            # Fallback: collect any date-like lines
            for ln in lines:
                if _DATE_RE.match(ln):
                    date_lines.append(ln)

        date_format = "UNKNOWN"
        if date_lines:
            # COMTRADE uses day/month/year — we do not silently reinterpret
            date_format = "DD/MM/YYYY"
            evidence.append(f"{len(date_lines)} date/time line(s); assuming dd/mm/yyyy per standard")

        conf = 0.3
        if date_lines:
            conf += 0.4
        if timemult is not None:
            conf += 0.2
        if has_2013:
            conf += 0.1

        return TimestampDetection(
            has_start_time=len(date_lines) >= 1,
            has_trigger_time=len(date_lines) >= 2,
            date_format=date_format,
            time_multiplier=timemult,
            has_2013_time_fields=has_2013,
            confidence=min(1.0, conf),
            evidence=evidence,
            notes=notes,
        )
