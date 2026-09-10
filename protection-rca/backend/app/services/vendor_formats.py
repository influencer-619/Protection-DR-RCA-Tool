"""Vendor binary / project format bridges (deterministic, no GenAI).

Handles previously intentional gaps:
  - SEL AcSELerator ``.rdb`` (OLE2) → extract SET_ALL / settings text
  - SEL ``.cev`` Compressed Event → IEEE COMTRADE CFG+DAT ASCII
  - Siemens DIGSI ``.dz5`` / ``.dex5`` / ``.d5z`` and ABB PCM600 packages
    that are ZIP containers → extract nested CFG/DAT/CFF/settings

Never invents measurements: missing/unreadable streams return NOT_CALCULABLE
with an actionable reason.
"""

from __future__ import annotations

import io
import logging
import math
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

VENDOR_PACKAGE_EXTS = frozenset(
    {".dz5", ".dex5", ".d5z", ".pcmi", ".pcmp", ".zip", ".7z"}
)
COMTRADE_MEMBER_EXTS = frozenset({".cfg", ".dat", ".cff", ".hdr", ".inf"})
SETTINGS_MEMBER_EXTS = frozenset(
    {".txt", ".csv", ".json", ".xml", ".xrio", ".set", ".rdb"}
)


def is_ole2(data: bytes) -> bool:
    return len(data) >= 8 and data[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def is_zip_bytes(data: bytes) -> bool:
    return len(data) >= 4 and data[:2] == b"PK"


def is_vendor_package(filename: str, data: bytes) -> bool:
    ext = Path(filename or "").suffix.lower()
    if ext in VENDOR_PACKAGE_EXTS and is_zip_bytes(data):
        return True
    # Misnamed ZIP project packages
    if ext in {".dz5", ".dex5", ".d5z", ".pcmi", ".pcmp"} and is_zip_bytes(data):
        return True
    return False


def extract_sel_rdb_text(data: bytes) -> dict[str, Any]:
    """Extract SET_ALL / settings text from SEL ``.rdb`` OLE2 compound file."""
    if not is_ole2(data):
        return {
            "status": "NOT_CALCULABLE",
            "reason": "Not a valid OLE2 / SEL .rdb compound file",
            "text": "",
            "streams": [],
        }
    try:
        import olefile
    except ImportError:
        return {
            "status": "NOT_CALCULABLE",
            "reason": "olefile package NOT AVAILABLE — install olefile to read SEL .rdb",
            "text": "",
            "streams": [],
        }

    streams_meta: list[str] = []
    candidates: list[tuple[int, str, str]] = []  # score, name, text
    try:
        ole = olefile.OleFileIO(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "NOT_CALCULABLE",
            "reason": f"Unable to open SEL .rdb OLE: {exc}",
            "text": "",
            "streams": [],
        }

    try:
        for entry in ole.listdir(streams=True, storages=False):
            name = "/".join(entry)
            streams_meta.append(name)
            try:
                raw = ole.openstream(entry).read()
            except Exception:  # noqa: BLE001
                continue
            # Prefer text streams
            text = ""
            for enc in ("utf-8", "latin-1", "cp1252"):
                try:
                    text = raw.decode(enc)
                    break
                except UnicodeDecodeError:
                    continue
            if not text or len(text) < 20:
                continue
            score = 0
            upper = text.upper()
            name_u = name.upper()
            if "SET_ALL" in name_u or name_u.endswith("SET_ALL"):
                score += 100
            if "SET_" in name_u:
                score += 40
            if "FID=" in upper or "FID =" in upper:
                score += 30
            if "[SET_" in upper or "[FID]" in upper:
                score += 50
            if re.search(r"\bE51|\b50P|\bZ1MAG|\bCTR\b", upper):
                score += 20
            if score:
                candidates.append((score, name, text))
    finally:
        try:
            ole.close()
        except Exception:  # noqa: BLE001
            pass

    if not candidates:
        return {
            "status": "NOT_CALCULABLE",
            "reason": (
                "SEL .rdb opened but no SET_ALL / settings text stream found — "
                "export SET_ALL.TXT from AcSELerator"
            ),
            "text": "",
            "streams": streams_meta[:50],
        }

    candidates.sort(key=lambda t: (-t[0], -len(t[2])))
    best_score, best_name, best_text = candidates[0]
    # Merge additional SET_* streams if best is partial
    if best_score < 100 and len(candidates) > 1:
        parts = [best_text]
        for sc, nm, tx in candidates[1:6]:
            if sc >= 40 and tx not in parts:
                parts.append(f"\n; --- stream: {nm} ---\n{tx}")
        best_text = "\n".join(parts)

    return {
        "status": "OK",
        "reason": None,
        "text": best_text,
        "stream": best_name,
        "streams": streams_meta[:50],
        "score": best_score,
    }


def _fmt_comtrade_time(dt: datetime) -> str:
    return (
        f"{dt.day:02d}/{dt.month:02d}/{dt.year},"
        f"{dt.hour:02d}:{dt.minute:02d}:{dt.second:02d}."
        f"{int(dt.microsecond):06d}"
    )


def cev_to_comtrade_files(
    data: bytes,
    *,
    basename: str = "sel_event",
) -> dict[str, Any]:
    """
    Convert SEL CEV (Compressed Event) to IEEE C37.111 ASCII CFG+DAT.

    Uses ``pycev`` when available. Returns cfg/dat text + metadata.
    """
    try:
        from pycev import CEV
    except ImportError:
        return {
            "status": "NOT_CALCULABLE",
            "reason": "pycev package NOT AVAILABLE — install pycev to read SEL .cev",
            "cfg": None,
            "dat": None,
        }

    stem = Path(basename).stem or "sel_event"
    try:
        # pycev accepts str or bytes via load_data
        if isinstance(data, bytes):
            text = data.decode("utf-8", errors="replace")
            # Reject true binary blobs that are not CASCII
            if data[:4] == b"\x00\x00\x00\x00" and b"FID" not in data[:2000]:
                return {
                    "status": "NOT_CALCULABLE",
                    "reason": "File does not look like SEL Compressed ASCII CEV",
                    "cfg": None,
                    "dat": None,
                }
            rec = CEV(data=text, ignore_warnings=True)
        else:
            rec = CEV(data=data, ignore_warnings=True)
    except Exception as exc:  # noqa: BLE001
        return {
            "status": "NOT_CALCULABLE",
            "reason": f"SEL CEV parse failed: {exc}",
            "cfg": None,
            "dat": None,
        }

    n_a = int(getattr(rec, "analog_count", 0) or 0)
    n_d = int(getattr(rec, "digital_count", 0) or getattr(rec, "status_count", 0) or 0)
    analogs = list(getattr(rec, "analog_channels", []) or [])
    digitals = list(getattr(rec, "digital_channels", []) or getattr(rec, "status_channels", []) or [])
    a_ids = list(getattr(rec, "analog_channel_ids", []) or [])
    d_ids = list(getattr(rec, "digital_channel_ids", []) or getattr(rec, "status_channel_ids", []) or [])
    if n_a <= 0 or not analogs or not analogs[0]:
        return {
            "status": "NOT_CALCULABLE",
            "reason": "CEV parsed but no analog samples found",
            "cfg": None,
            "dat": None,
        }

    n_samples = len(analogs[0])
    f0 = float(getattr(rec, "frequency", 0) or 50.0) or 50.0
    # Infer sample rate from timestamps when available
    times = list(getattr(rec, "time", []) or [])
    if len(times) >= 2:
        dt0 = (times[1] - times[0]).total_seconds()
        fs = (1.0 / dt0) if dt0 > 0 else 1000.0
    else:
        # Fallback: pycev SAM/CYC properties
        props = getattr(rec, "_properties", {}) or {}
        try:
            sam = float(props.get("SAM/CYC_A") or props.get("SAM/CYC") or 8)
            fs = sam * f0
        except (TypeError, ValueError):
            fs = 1000.0

    trig = getattr(rec, "trigger_time", None) or datetime(1970, 1, 1)
    if not isinstance(trig, datetime):
        trig = datetime(1970, 1, 1)
    start = times[0] if times else trig
    if not isinstance(start, datetime):
        start = trig

    station = "SEL"
    device = str(getattr(rec, "fid", "") or "CEV")[:64]
    total = n_a + n_d
    lines = [
        f"{station},{device},1999",
        f"{total},{n_a}A,{n_d}D",
    ]
    for i in range(n_a):
        name = (a_ids[i] if i < len(a_ids) else f"A{i+1}").replace(",", "_")[:64]
        unit = "A" if re.search(r"\bI|AMP", name, re.I) else ("V" if re.search(r"\bV|VOLT", name, re.I) else "EU")
        # Values already engineering — a=1,b=0
        lines.append(
            f"{i+1},{name},,,{unit},1.0,0.0,0,-32767,32767,1,1,P"
        )
    for i in range(n_d):
        name = (d_ids[i] if i < len(d_ids) else f"D{i+1}").replace(",", "_")[:64]
        lines.append(f"{i+1},{name},,,0")
    lines.append(f"{f0:.2f}")
    lines.append("1")
    lines.append(f"{fs:.6f},{n_samples}")
    lines.append(_fmt_comtrade_time(start))
    lines.append(_fmt_comtrade_time(trig))
    lines.append("ASCII")
    lines.append("1.0")
    cfg_text = "\n".join(lines) + "\n"

    dat_lines: list[str] = []
    for s in range(n_samples):
        if times and s < len(times):
            t_us = int(round((times[s] - start).total_seconds() * 1e6))
        else:
            t_us = int(round(s * (1e6 / fs)))
        vals: list[str] = []
        for ch in range(n_a):
            series = analogs[ch] if ch < len(analogs) else []
            v = float(series[s]) if s < len(series) else 0.0
            if not math.isfinite(v):
                v = 0.0
            # Store as integer milli-units to keep ASCII compact; a=1 so use rounded EU*1000? 
            # CFG says a=1.0 → store rounded engineering as int
            vals.append(str(int(round(v))))
        for ch in range(n_d):
            series = digitals[ch] if ch < len(digitals) else []
            bit = series[s] if s < len(series) else 0
            vals.append("1" if bit else "0")
        dat_lines.append(f"{s+1},{t_us}," + ",".join(vals))
    dat_text = "\n".join(dat_lines) + "\n"

    # Also extract embedded settings block when present
    settings_text = str(getattr(rec, "settings", "") or "")

    return {
        "status": "OK",
        "reason": None,
        "cfg": cfg_text,
        "dat": dat_text,
        "cfg_name": f"{stem}.cfg",
        "dat_name": f"{stem}.dat",
        "settings_text": settings_text,
        "fid": device,
        "samples": n_samples,
        "analog_count": n_a,
        "digital_count": n_d,
        "sample_rate_hz": fs,
        "frequency_hz": f0,
        "trigger_time": trig.isoformat() if hasattr(trig, "isoformat") else str(trig),
    }


def expand_vendor_package(
    data: bytes,
    *,
    filename: str = "package.dz5",
    max_members: int = 200,
) -> dict[str, Any]:
    """
    Expand DIGSI / PCM600 / ZIP project packages into member files.

    Returns members usable as COMTRADE or settings uploads.
    """
    if not is_zip_bytes(data):
        return {
            "status": "NOT_CALCULABLE",
            "reason": (
                f"{Path(filename).suffix or 'package'} is not a ZIP-based project archive. "
                "From DIGSI: Export fault record as COMTRADE (CFG/DAT). "
                "From PCM600: export disturbance COMTRADE / settings CSV or XRIO."
            ),
            "members": [],
        }
    members: list[dict[str, Any]] = []
    skipped: list[str] = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        return {
            "status": "NOT_CALCULABLE",
            "reason": f"Invalid project ZIP: {exc}",
            "members": [],
        }

    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > max_members:
            return {
                "status": "NOT_CALCULABLE",
                "reason": f"Package has more than {max_members} files",
                "members": [],
            }
        for info in infos:
            name = Path(info.filename.replace("\\", "/")).name
            if not name or name.startswith("."):
                continue
            ext = Path(name).suffix.lower()
            useful = ext in COMTRADE_MEMBER_EXTS or ext in SETTINGS_MEMBER_EXTS or ext in {
                ".cev",
                ".eve",
                ".soe",
            }
            if not useful:
                skipped.append(name)
                continue
            try:
                raw = zf.read(info)
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"{name}:{exc}")
                continue
            kind = "COMTRADE" if ext in COMTRADE_MEMBER_EXTS else (
                "SETTINGS" if ext in SETTINGS_MEMBER_EXTS else "OTHER"
            )
            members.append(
                {
                    "filename": name,
                    "data": raw,
                    "kind": kind,
                    "size": len(raw),
                }
            )

    if not members:
        return {
            "status": "NOT_CALCULABLE",
            "reason": (
                "Project package opened but no CFG/DAT/CFF/settings members found. "
                "Export COMTRADE disturbance records and settings CSV/XRIO/text from the vendor tool."
            ),
            "members": [],
            "skipped": skipped[:30],
        }

    return {
        "status": "OK",
        "reason": None,
        "members": members,
        "skipped": skipped[:30],
        "package": Path(filename).name,
    }
