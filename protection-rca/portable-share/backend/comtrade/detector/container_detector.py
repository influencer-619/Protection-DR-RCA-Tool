"""Detect COMTRADE container type: CFG+DAT pair vs single-file CFF."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from comtrade._io import FilePath, classify_paths, looks_like_cff_text, read_bytes, sniff_text
from comtrade.detector.format_detector import FormatDetection


@dataclass
class ContainerDetection:
    container: str  # CFG_DAT | CFF | UNKNOWN
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)
    cfg_path: Optional[Path] = None
    dat_path: Optional[Path] = None
    cff_path: Optional[Path] = None


def _pair_cfg_dat(
    cfgs: list[Path], dats: list[Path]
) -> tuple[Optional[Path], Optional[Path], str]:
    """Prefer same-stem CFG+DAT pairs; fall back to first of each."""
    if not cfgs and not dats:
        return None, None, "none"
    dat_by_stem = {p.stem.lower(): p for p in dats}
    for cfg in cfgs:
        match = dat_by_stem.get(cfg.stem.lower())
        if match is not None:
            return cfg, match, "stem"
    # Case-insensitive stem with common suffixes stripped (_cfg/_dat already gone via stem)
    for cfg in cfgs:
        stem = cfg.stem.lower().replace("_cfg", "").replace("-cfg", "")
        for dat in dats:
            dstem = dat.stem.lower().replace("_dat", "").replace("-dat", "")
            if stem == dstem or stem in dstem or dstem in stem:
                return cfg, dat, "fuzzy-stem"
    cfg = cfgs[0] if cfgs else None
    dat = dats[0] if dats else None
    return cfg, dat, "first"


class ComtradeContainerDetector:
    """Determine whether the record is multi-file CFG/DAT or single-file CFF."""

    def detect(
        self,
        files: Sequence[FilePath],
        format_hint: Optional[FormatDetection] = None,
    ) -> ContainerDetection:
        groups = classify_paths(files)
        evidence: list[str] = []

        for path in files:
            text = sniff_text(read_bytes(path, max_bytes=65536))
            if looks_like_cff_text(text):
                evidence.append(f"CFF markers in {path}")
                return ContainerDetection(
                    container="CFF",
                    confidence=0.95,
                    evidence=evidence,
                    cff_path=Path(path),
                )

        if format_hint and format_hint.cff_path:
            return ContainerDetection(
                container="CFF",
                confidence=0.9,
                evidence=["format detector supplied CFF path"],
                cff_path=format_hint.cff_path,
            )

        cfgs = list(groups["cfg"])
        dats = list(groups["dat"])
        if format_hint and format_hint.cfg_path and format_hint.cfg_path not in cfgs:
            cfgs.insert(0, format_hint.cfg_path)
        if format_hint and format_hint.dat_path and format_hint.dat_path not in dats:
            dats.insert(0, format_hint.dat_path)

        cff = groups["cff"][0] if groups["cff"] else None
        if cff is not None:
            evidence.append(f".cff extension: {cff}")
            return ContainerDetection(
                container="CFF",
                confidence=0.7,
                evidence=evidence,
                cff_path=cff,
            )

        cfg, dat, how = _pair_cfg_dat(cfgs, dats)
        if cfg is not None and dat is not None:
            evidence.append(f"CFG+DAT pair ({how}): {cfg.name} + {dat.name}")
            conf = 0.95 if how == "stem" else (0.85 if how == "fuzzy-stem" else 0.7)
            return ContainerDetection(
                container="CFG_DAT",
                confidence=conf,
                evidence=evidence,
                cfg_path=cfg,
                dat_path=dat,
            )

        if cfg is not None:
            evidence.append("CFG present without DAT — incomplete CFG_DAT container")
            return ContainerDetection(
                container="CFG_DAT",
                confidence=0.4,
                evidence=evidence,
                cfg_path=cfg,
            )

        return ContainerDetection(
            container="UNKNOWN",
            confidence=0.0,
            evidence=["unable to determine container"],
        )
