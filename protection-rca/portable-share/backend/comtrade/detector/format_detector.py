"""Detect whether inputs are COMTRADE records (CFG+DAT or CFF)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from comtrade._io import (
    FilePath,
    classify_paths,
    looks_like_cff_text,
    looks_like_cfg_text,
    read_bytes,
    sniff_text,
)


@dataclass
class FormatDetection:
    is_comtrade: bool
    evidence: list[str] = field(default_factory=list)
    cfg_path: Optional[Path] = None
    dat_path: Optional[Path] = None
    cff_path: Optional[Path] = None
    confidence: float = 0.0


class ComtradeFormatDetector:
    """Decide if a file set is a COMTRADE record by inspecting contents."""

    def detect(self, files: Sequence[FilePath]) -> FormatDetection:
        groups = classify_paths(files)
        evidence: list[str] = []
        confidence = 0.0
        cfg_path = groups["cfg"][0] if groups["cfg"] else None
        dat_path = groups["dat"][0] if groups["dat"] else None
        cff_path = groups["cff"][0] if groups["cff"] else None

        # Prefer explicit CFF by content
        candidates = list(files)
        for path in candidates:
            data = read_bytes(path, max_bytes=65536)
            text = sniff_text(data)
            if looks_like_cff_text(text):
                evidence.append(f"CFF section markers in {path}")
                return FormatDetection(
                    is_comtrade=True,
                    evidence=evidence,
                    cff_path=Path(path),
                    confidence=0.95,
                )

        if cfg_path is not None:
            cfg_text = sniff_text(read_bytes(cfg_path, max_bytes=65536))
            if looks_like_cfg_text(cfg_text):
                evidence.append(f"CFG structure recognized in {cfg_path}")
                confidence += 0.55
            else:
                evidence.append(f"CFG extension present but content weak: {cfg_path}")
                confidence += 0.15

        if dat_path is not None:
            evidence.append(f"DAT file present: {dat_path}")
            confidence += 0.25
            # Peek: ASCII DAT starts with sample number / commas; binary is opaque
            dat_head = read_bytes(dat_path, max_bytes=256)
            head_text = sniff_text(dat_head)
            first_line = head_text.splitlines()[0] if head_text.splitlines() else ""
            if "," in first_line and first_line[:1].isdigit():
                evidence.append("DAT head looks ASCII CSV")
                confidence += 0.1
            else:
                evidence.append("DAT head looks binary")
                confidence += 0.05

        # Content-only scan when extensions are missing / wrong
        if confidence < 0.5:
            for path in candidates:
                text = sniff_text(read_bytes(path, max_bytes=65536))
                if looks_like_cfg_text(text):
                    evidence.append(f"CFG-like content without .cfg extension: {path}")
                    cfg_path = Path(path)
                    confidence = max(confidence, 0.7)
                    break

        is_comtrade = confidence >= 0.5 or (cfg_path is not None and dat_path is not None)
        if cfg_path and dat_path:
            confidence = max(confidence, 0.8)
            is_comtrade = True

        return FormatDetection(
            is_comtrade=is_comtrade,
            evidence=evidence,
            cfg_path=cfg_path,
            dat_path=dat_path,
            cff_path=cff_path,
            confidence=min(1.0, confidence),
        )
