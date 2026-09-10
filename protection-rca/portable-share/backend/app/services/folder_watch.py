"""Optional folder / path auto-ingest for COMTRADE packages (no OT control)."""

from __future__ import annotations

import hashlib
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_COMTRADE_EXTS = {
    ".cfg",
    ".dat",
    ".cff",
    ".hdr",
    ".inf",
    ".zip",
    ".cev",
    ".dz5",
    ".dex5",
    ".d5z",
    ".pcmi",
    ".pcmp",
    ".rdb",
}


def scan_ingest_folder(
    folder: str | Path,
    *,
    seen_hashes: Optional[set[str]] = None,
    max_files: int = 50,
) -> dict[str, Any]:
    """
    Scan a local folder for new COMTRADE / ZIP packages.

    Returns candidate file paths; does not write to the database by itself.
    Caller (API / background job) creates events and uploads.
    """
    root = Path(folder)
    seen = set(seen_hashes or ())
    if not root.is_dir():
        return {
            "status": "NOT_AVAILABLE",
            "folder": str(root),
            "candidates": [],
            "reason": "Folder does not exist or is not a directory",
        }

    candidates: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _COMTRADE_EXTS:
            continue
        # Prefer .cfg / .cff / .zip as package anchors (skip lone .dat)
        if path.suffix.lower() == ".dat":
            cfg = path.with_suffix(".cfg")
            if cfg.exists():
                continue
        try:
            raw = path.read_bytes()[:1_048_576]
            digest = hashlib.sha256(raw + path.name.encode()).hexdigest()
        except OSError as exc:
            logger.warning("scan skip %s: %s", path, exc)
            continue
        if digest in seen:
            continue
        candidates.append(
            {
                "path": str(path.resolve()),
                "name": path.name,
                "size": path.stat().st_size,
                "mtime": path.stat().st_mtime,
                "sha256_prefix": digest,
            }
        )
        if len(candidates) >= max_files:
            break

    return {
        "status": "OK",
        "folder": str(root.resolve()),
        "candidates": candidates,
        "count": len(candidates),
        "notes": "Watch-only scan — upload/create event via API to ingest",
    }


def default_watch_folder() -> Optional[str]:
    env = os.environ.get("PROTECTION_RCA_WATCH_FOLDER") or os.environ.get("PES_WATCH_FOLDER")
    if env and Path(env).is_dir():
        return str(Path(env).resolve())
    return None


def poll_once(folder: Optional[str] = None) -> dict[str, Any]:
    """Single poll suitable for a lightweight scheduler tick."""
    path = folder or default_watch_folder()
    if not path:
        return {
            "status": "NOT_CONFIGURED",
            "candidates": [],
            "reason": "Set PROTECTION_RCA_WATCH_FOLDER to enable auto-ingest scanning",
            "polled_at": time.time(),
        }
    result = scan_ingest_folder(path)
    result["polled_at"] = time.time()
    return result
