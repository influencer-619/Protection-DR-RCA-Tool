"""Detect COMTRADE standard revision from CFG contents."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VersionDetection:
    standard: str  # IEEE | IEC | UNKNOWN
    revision: str  # 1991 | 1999 | 2001 | 2013 | UNKNOWN
    year_field: Optional[str] = None
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


class ComtradeVersionDetector:
    """Infer IEEE/IEC revision from CFG first-line year and trailing fields.

    Rules (content-based, not filename):
    - Missing / empty year on line 1 → likely 1991 (IEEE C37.111-1991)
    - Year 1999 → IEEE 1999 (also maps to IEC 60255-24:2001 content-wise)
    - Year 2013 → IEEE 2013 / IEC 60255-24:2013
    - Presence of BINARY32 / FLOAT32 or time_code lines → 2013
    - Presence of primary/secondary/PS on analog lines → at least 1999
    """

    _YEAR_RE = re.compile(r"\b(1991|1999|2001|2013)\b")

    def detect(self, cfg_text: str, *, prefer_iec: bool = False) -> VersionDetection:
        lines = [ln.strip() for ln in cfg_text.splitlines() if ln.strip()]
        evidence: list[str] = []
        notes: list[str] = []
        year_field: Optional[str] = None
        confidence = 0.4

        if not lines:
            return VersionDetection(
                standard="UNKNOWN",
                revision="UNKNOWN",
                confidence=0.0,
                evidence=["empty CFG"],
            )

        # Line 1: station,device,year
        parts = [p.strip() for p in lines[0].split(",")]
        if len(parts) >= 3 and parts[2]:
            year_field = parts[2].strip()
            evidence.append(f"CFG year field: {year_field}")
            confidence += 0.25
        else:
            evidence.append("CFG year field absent → candidate 1991")
            notes.append("1991 CFG omits revision year on first line")

        upper = cfg_text.upper()
        has_2013_ft = any(tok in upper for tok in ("BINARY32", "FLOAT32"))
        # 2013 trailing time quality lines: after timemult, two more lines
        has_ps_fields = self._has_primary_secondary(lines)
        has_time_code_line = self._looks_like_2013_trailer(lines)

        revision = "UNKNOWN"
        standard = "IEEE"

        if year_field:
            m = self._YEAR_RE.search(year_field)
            if m:
                y = m.group(1)
                if y == "1991":
                    revision = "1991"
                elif y == "1999":
                    revision = "1999"
                elif y == "2001":
                    revision = "2001"
                    standard = "IEC"
                elif y == "2013":
                    revision = "2013"
                confidence += 0.2

        if revision == "UNKNOWN":
            if has_2013_ft or has_time_code_line:
                revision = "2013"
                evidence.append("2013 markers (BINARY32/FLOAT32 or time_code trailer)")
                confidence += 0.2
            elif has_ps_fields:
                revision = "1999"
                evidence.append("primary/secondary/PS fields → ≥1999")
                confidence += 0.15
            elif year_field is None:
                revision = "1991"
                confidence += 0.15

        # IEC preference / dual-logo mapping
        if prefer_iec:
            standard = "IEC"
            if revision == "1999":
                notes.append("IEEE 1999 content treated as IEC 60255-24:2001 equivalent")
                revision = "2001"
            elif revision == "2013":
                notes.append("IEEE 2013 content treated as IEC 60255-24:2013")
        else:
            if revision == "2001":
                standard = "IEC"
            elif revision == "2013" and "IEC" in (year_field or "").upper():
                standard = "IEC"
            else:
                standard = "IEEE"

        if has_2013_ft and revision not in ("2013",):
            notes.append("BINARY32/FLOAT32 present but year ≠ 2013 — marking 2013 features")
            if revision in ("UNKNOWN", "1999", "2001"):
                revision = "2013"
                confidence = max(confidence, 0.75)

        return VersionDetection(
            standard=standard,
            revision=revision,
            year_field=year_field,
            confidence=min(1.0, confidence),
            evidence=evidence,
            notes=notes,
        )

    @staticmethod
    def _has_primary_secondary(lines: list[str]) -> bool:
        """Analog lines in 1999+ have 13 fields including primary,secondary,PS."""
        for ln in lines[2:]:
            parts = [p.strip() for p in ln.split(",")]
            if len(parts) >= 13:
                ps = parts[12].upper()
                if ps in ("P", "S"):
                    return True
        return False

    @staticmethod
    def _looks_like_2013_trailer(lines: list[str]) -> bool:
        """2013 adds time_code,local_code and tmq_code,leapsec after timemult."""
        if len(lines) < 6:
            return False
        # Scan near end for short comma pairs that are not dates
        for ln in lines[-4:]:
            parts = [p.strip() for p in ln.split(",")]
            if len(parts) == 2 and not re.match(r"\d{1,2}/\d{1,2}/", parts[0]):
                # Could be time_code line or tmq line
                if parts[0].upper() in ("ASCII", "BINARY", "BINARY32", "FLOAT32"):
                    continue
                try:
                    float(parts[0])
                    # timemult is a single float — skip
                    if len(parts) == 1 or (
                        len(parts) == 2 and parts[1] == ""
                    ):
                        continue
                except ValueError:
                    return True
                # tmq_code is often a digit / letter pair
                if re.match(r"^[0-9F]$", parts[0], re.I) or parts[0] in ("0", "1"):
                    return True
        return False
