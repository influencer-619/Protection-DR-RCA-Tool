"""Shared file I/O helpers for COMTRADE detection and parsing."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence, Union

FilePath = Union[str, Path]


def as_path(path: FilePath) -> Path:
    return Path(path)


def read_bytes(path: FilePath, max_bytes: Optional[int] = None) -> bytes:
    p = as_path(path)
    with p.open("rb") as fh:
        return fh.read() if max_bytes is None else fh.read(max_bytes)


def read_text_lossy(path: FilePath, max_bytes: Optional[int] = None) -> str:
    """Read file as text, trying UTF-8 then latin-1. Never raises on decode."""
    data = read_bytes(path, max_bytes)
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


def sniff_text(data: bytes, max_chars: int = 8192) -> str:
    chunk = data[:max_chars]
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return chunk.decode(enc)
        except UnicodeDecodeError:
            continue
    return chunk.decode("latin-1", errors="replace")


def classify_paths(files: Sequence[FilePath]) -> dict[str, list[Path]]:
    """Group paths by lowercase extension."""
    groups: dict[str, list[Path]] = {
        "cfg": [],
        "dat": [],
        "cff": [],
        "hdr": [],
        "inf": [],
        "other": [],
    }
    for f in files:
        p = as_path(f)
        ext = p.suffix.lower().lstrip(".")
        if ext in groups:
            groups[ext].append(p)
        else:
            groups["other"].append(p)
    return groups


def looks_like_cfg_text(text: str) -> bool:
    """Heuristic: CFG has comma-separated header and a channel-count line."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 4:
        return False
    # Line 2 typically: TT,##A,##D  or just TT for 1991
    second = lines[1].upper()
    if "A" in second or second.replace(",", "").isdigit():
        # Look for ASCII/BINARY/ft marker somewhere
        upper = text.upper()
        if any(tok in upper for tok in ("ASCII", "BINARY", "FLOAT32", "BINARY32")):
            return True
        # Or look for date-like lines dd/mm/yyyy
        import re

        if re.search(r"\d{1,2}/\d{1,2}/\d{2,4}", text):
            return True
    return False


def looks_like_cff_text(text: str) -> bool:
    upper = text.upper()
    return "--- FILE TYPE:" in upper or "FILE TYPE: CFG" in upper


def first_nonempty_lines(text: str, n: int = 30) -> list[str]:
    out: list[str] = []
    for ln in text.splitlines():
        s = ln.strip()
        if s:
            out.append(s)
            if len(out) >= n:
                break
    return out


def join_unique(paths: Iterable[FilePath]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for p in paths:
        s = str(as_path(p))
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out
