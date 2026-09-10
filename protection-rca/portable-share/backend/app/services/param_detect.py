"""Flexible detection of CT/VT / line parameters from arbitrary settings JSON.

Does **not** require fixed field names. Walks nested dict/list structures and
maps keys by normalized tokens (spaces/underscores/punctuation ignored) and
common engineering synonyms. Never invents numeric values — only reshapes
what is present.
"""

from __future__ import annotations

import math
import re
from typing import Any, Iterator, Optional


def _norm_key(key: Any) -> str:
    s = str(key or "").strip().lower()
    s = s.replace("Ω", "ohm").replace("ω", "ohm")
    s = re.sub(r"[^a-z0-9]+", "", s)
    return s


def _walk(obj: Any, path: str = "") -> Iterator[tuple[str, str, Any]]:
    """Yield (path, normalized_key, value) for every leaf / useful node."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            nk = _norm_key(k)
            p = f"{path}.{k}" if path else str(k)
            yield p, nk, v
            if isinstance(v, (dict, list)):
                yield from _walk(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            p = f"{path}[{i}]"
            if isinstance(v, (dict, list)):
                yield from _walk(v, p)
            else:
                yield p, "", v


def _looks_ratio_string(v: Any) -> bool:
    if not isinstance(v, str):
        return False
    s = v.strip().replace(" ", "")
    return bool(re.fullmatch(r"\d+(\.\d+)?\s*[/:]\s*\d+(\.\d+)?", s))


def _as_float(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        return x if math.isfinite(x) else None
    if isinstance(v, str):
        s = v.strip().replace(",", "")
        if not s or s.upper() in ("NA", "N/A", "NONE", "NULL", "-", "UNKNOWN"):
            return None
        # strip units
        s2 = re.sub(r"(?i)\s*(a|amp|amps|v|kv|ohm|ohms|km|m|%|pu)\s*$", "", s).strip()
        try:
            x = float(s2)
            return x if math.isfinite(x) else None
        except ValueError:
            return None
    return None


def _score_key(nk: str, *needles: str) -> int:
    """Higher score = better match; all needles must appear as substrings of nk."""
    if not nk:
        return 0
    if all(n in nk for n in needles):
        return 10 + sum(len(n) for n in needles)
    return 0


def _best(
    items: list[tuple[int, str, Any]],
) -> Optional[tuple[str, Any]]:
    if not items:
        return None
    items.sort(key=lambda t: (-t[0], len(t[1])))
    return items[0][1], items[0][2]


def detect_plant_parameters(data: Any) -> dict[str, Any]:
    """Detect CT/VT and line parameters from any JSON-like object.

    Returns:
      {
        "ct_vt": {...normalized fields...},
        "line": {...normalized fields...},
        "detected_keys": {canonical: original_path},
      }
    """
    from fault_analysis.location import normalize_ct_vt, normalize_line_params, parse_ratio_value

    if not isinstance(data, dict):
        return {"ct_vt": {}, "line": {}, "detected_keys": {}}

    ct_ratio_cands: list[tuple[int, str, Any]] = []
    vt_ratio_cands: list[tuple[int, str, Any]] = []
    ct_pri: list[tuple[int, str, Any]] = []
    ct_sec: list[tuple[int, str, Any]] = []
    vt_pri: list[tuple[int, str, Any]] = []
    vt_sec: list[tuple[int, str, Any]] = []
    length: list[tuple[int, str, Any]] = []
    r1: list[tuple[int, str, Any]] = []
    x1: list[tuple[int, str, Any]] = []
    r0: list[tuple[int, str, Any]] = []
    x0: list[tuple[int, str, Any]] = []
    z1mag: list[tuple[int, str, Any]] = []
    z0mag: list[tuple[int, str, Any]] = []

    for path, nk, val in _walk(data):
        if val is None or val == "":
            continue
        # Skip huge nested blobs already walked as children
        if isinstance(val, (dict, list)):
            continue

        # --- CT ratio ---
        sc = max(
            _score_key(nk, "ctratio"),
            _score_key(nk, "ct", "ratio"),
            _score_key(nk, "currenttransformer", "ratio"),
            _score_key(nk, "ctr") if nk in ("ctr", "ctrt", "ctratio") else 0,
            8 if nk in ("ct", "ctratio", "ctratioa", "ctratioamp") and _looks_ratio_string(val) else 0,
        )
        # Avoid false positive: "reactance", "protect", etc.
        if "react" in nk or "protect" in nk or "contact" in nk:
            sc = 0
        if sc and (parse_ratio_value(val) is not None or _looks_ratio_string(val) or _as_float(val)):
            ct_ratio_cands.append((sc, path, val))

        # --- VT / PT ratio ---
        sc = max(
            _score_key(nk, "vtratio"),
            _score_key(nk, "ptratio"),
            _score_key(nk, "vt", "ratio"),
            _score_key(nk, "pt", "ratio"),
            _score_key(nk, "voltagetransformer", "ratio"),
            _score_key(nk, "potentialtransformer", "ratio"),
            _score_key(nk, "vtr") if nk in ("vtr", "ptr", "vtratio", "ptratio") else 0,
            8 if nk in ("vt", "pt", "cvt", "vtpt") and _looks_ratio_string(val) else 0,
        )
        if sc and (parse_ratio_value(val) is not None or _looks_ratio_string(val) or _as_float(val)):
            vt_ratio_cands.append((sc, path, val))

        # CT primary / secondary
        sc = max(
            _score_key(nk, "ct", "primary"),
            _score_key(nk, "ctprimary"),
            _score_key(nk, "ct", "pri"),
        )
        if sc and _as_float(val) is not None:
            ct_pri.append((sc, path, val))
        sc = max(
            _score_key(nk, "ct", "secondary"),
            _score_key(nk, "ctsecondary"),
            _score_key(nk, "ct", "sec"),
        )
        if sc and _as_float(val) is not None:
            ct_sec.append((sc, path, val))

        # VT primary / secondary
        sc = max(
            _score_key(nk, "vt", "primary"),
            _score_key(nk, "pt", "primary"),
            _score_key(nk, "vtprimary"),
            _score_key(nk, "ptprimary"),
        )
        if sc and _as_float(val) is not None:
            vt_pri.append((sc, path, val))
        sc = max(
            _score_key(nk, "vt", "secondary"),
            _score_key(nk, "pt", "secondary"),
            _score_key(nk, "vtsecondary"),
            _score_key(nk, "ptsecondary"),
        )
        if sc and _as_float(val) is not None:
            vt_sec.append((sc, path, val))

        # Line length
        sc = max(
            _score_key(nk, "length", "km"),
            _score_key(nk, "linelength"),
            _score_key(nk, "line", "length"),
            _score_key(nk, "feeder", "length"),
            6 if nk in ("length", "lengthkm", "lenkm") else 0,
        )
        if sc and _as_float(val) is not None:
            length.append((sc, path, val))

        # Positive-sequence R/X
        sc = max(
            _score_key(nk, "positivesequence", "r"),
            _score_key(nk, "positive", "r", "ohm"),
            _score_key(nk, "r1", "ohm"),
            9 if nk in ("r1", "r1ohmpkm", "r1ohmperkm", "posr", "z1r") else 0,
        )
        if sc and _as_float(val) is not None:
            r1.append((sc, path, val))
        sc = max(
            _score_key(nk, "positivesequence", "x"),
            _score_key(nk, "positive", "x", "ohm"),
            _score_key(nk, "x1", "ohm"),
            9 if nk in ("x1", "x1ohmpkm", "x1ohmperkm", "posx", "z1x") else 0,
        )
        if sc and _as_float(val) is not None:
            x1.append((sc, path, val))

        # Zero-sequence R/X
        sc = max(
            _score_key(nk, "zerosequence", "r"),
            _score_key(nk, "zero", "r", "ohm"),
            9 if nk in ("r0", "r0ohmpkm", "r0ohmperkm", "zeror", "z0r") else 0,
        )
        if sc and _as_float(val) is not None:
            r0.append((sc, path, val))
        sc = max(
            _score_key(nk, "zerosequence", "x"),
            _score_key(nk, "zero", "x", "ohm"),
            9 if nk in ("x0", "x0ohmpkm", "x0ohmperkm", "zerox", "z0x") else 0,
        )
        if sc and _as_float(val) is not None:
            x0.append((sc, path, val))

        sc = max(
            _score_key(nk, "z1", "ohm"),
            _score_key(nk, "positivesequence", "z"),
            8 if nk in ("z1", "z1ohm", "z1ohmpkm") else 0,
        )
        if sc and _as_float(val) is not None:
            z1mag.append((sc, path, val))
        sc = max(
            _score_key(nk, "z0", "ohm"),
            _score_key(nk, "zerosequence", "z"),
            8 if nk in ("z0", "z0ohm", "z0ohmpkm") else 0,
        )
        if sc and _as_float(val) is not None:
            z0mag.append((sc, path, val))

    detected: dict[str, str] = {}
    ct_raw: dict[str, Any] = {}
    line_raw: dict[str, Any] = {}

    b = _best(ct_ratio_cands)
    if b:
        ct_raw["ct_ratio"] = b[1]
        detected["ct_ratio"] = b[0]
    b = _best(vt_ratio_cands)
    if b:
        ct_raw["vt_ratio"] = b[1]
        detected["vt_ratio"] = b[0]
    b = _best(ct_pri)
    if b:
        ct_raw["ct_primary_a"] = _as_float(b[1])
        detected["ct_primary_a"] = b[0]
    b = _best(ct_sec)
    if b:
        ct_raw["ct_secondary_a"] = _as_float(b[1])
        detected["ct_secondary_a"] = b[0]
    b = _best(vt_pri)
    if b:
        ct_raw["vt_primary_v"] = _as_float(b[1])
        detected["vt_primary_v"] = b[0]
    b = _best(vt_sec)
    if b:
        ct_raw["vt_secondary_v"] = _as_float(b[1])
        detected["vt_secondary_v"] = b[0]

    b = _best(length)
    if b:
        line_raw["length_km"] = _as_float(b[1])
        detected["length_km"] = b[0]
    b = _best(r1)
    if b:
        line_raw["positive_sequence_r_ohm_per_km"] = _as_float(b[1])
        detected["positive_sequence_r_ohm_per_km"] = b[0]
    b = _best(x1)
    if b:
        line_raw["positive_sequence_x_ohm_per_km"] = _as_float(b[1])
        detected["positive_sequence_x_ohm_per_km"] = b[0]
    b = _best(r0)
    if b:
        line_raw["zero_sequence_r_ohm_per_km"] = _as_float(b[1])
        detected["zero_sequence_r_ohm_per_km"] = b[0]
    b = _best(x0)
    if b:
        line_raw["zero_sequence_x_ohm_per_km"] = _as_float(b[1])
        detected["zero_sequence_x_ohm_per_km"] = b[0]
    # Magnitude-only Z1/Z0 as last resort (stored for display; location prefers R+jX)
    b = _best(z1mag)
    if b and "positive_sequence_r_ohm_per_km" not in line_raw:
        line_raw["z1_magnitude_ohm_per_km"] = _as_float(b[1])
        detected["z1_magnitude_ohm_per_km"] = b[0]
    b = _best(z0mag)
    if b and "zero_sequence_r_ohm_per_km" not in line_raw:
        line_raw["z0_magnitude_ohm_per_km"] = _as_float(b[1])
        detected["z0_magnitude_ohm_per_km"] = b[0]

    ct_vt = normalize_ct_vt(ct_raw)
    line = normalize_line_params(line_raw)
    return {"ct_vt": ct_vt, "line": line, "detected_keys": detected}


def line_ct_vt_from_any(data: Any) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    """Convenience wrapper used by ingest/analysis."""
    det = detect_plant_parameters(data)
    return det["ct_vt"], det["line"], det["detected_keys"]


_KV_EXPLICIT_KEYS = frozenset(
    {
        "nominalvoltagekv",
        "nominalsystemvoltage",
        "nominalsystemvoltagekv",
        "systemvoltagekv",
        "ratedvoltagekv",
        "vnomkv",
        "vnkv",
        "unomkv",
        "linevoltagekv",
        "voltagelevelkv",
        "kv",
    }
)

_KV_TEXT_PATTERNS = (
    re.compile(
        r"(?i)nominal\s+system\s+voltage\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*kV"
    ),
    re.compile(
        r"(?i)(?:system|rated|line|bus|nominal)\s*voltage\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)\s*kV"
    ),
    re.compile(r"(?i)\b([0-9]{2,4}(?:\.[0-9]+)?)\s*kV\b"),
)

_VT_RATIO_RE = re.compile(
    r"(?i)\b(?:vt|pt|voltage\s*transformer)?\s*ratio\s*[:=]?\s*"
    r"([0-9]{3,7}(?:\.[0-9]+)?)\s*[/:]\s*([0-9]+(?:\.[0-9]+)?)"
)
_VT_RATIO_BARE = re.compile(
    r"(?i)\b([0-9]{4,7})\s*[/:]\s*([0-9]{2,4})\b"  # e.g. 132000/110
)


def _sane_kv(val: Optional[float]) -> Optional[float]:
    if val is None:
        return None
    try:
        x = float(val)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x) or x <= 0:
        return None
    # Accept common HV/MV range; reject secondary volts mistaken as kV
    if 0.38 <= x <= 1200:
        return round(x, 3) if x < 10 else (round(x, 1) if x != int(x) else float(int(x)))
    return None


def _kv_from_vt_primary_volts(primary_v: float) -> Optional[float]:
    """132000 V → 132 kV; 11000 → 11 kV."""
    if primary_v >= 1000:
        return _sane_kv(primary_v / 1000.0)
    # Already in kV (e.g. 132/0.11)
    return _sane_kv(primary_v)


def extract_nominal_voltage_kv(
    *,
    json_blobs: Optional[list[Any]] = None,
    texts: Optional[list[str]] = None,
    filenames: Optional[list[str]] = None,
    station: Optional[str] = None,
) -> tuple[Optional[float], Optional[str]]:
    """
    Derive nominal system voltage (kV) from settings / names when present.

    Never invents — returns (None, None) if no explicit evidence.
    Priority: explicit JSON keys → settings text → VT primary → filename/station.
    """
    # 1) Explicit JSON keys / nested plant params
    for blob in json_blobs or []:
        if not isinstance(blob, dict):
            continue
        for path, nk, val in _walk(blob):
            if nk in _KV_EXPLICIT_KEYS or (
                "nominal" in nk and "voltage" in nk and ("kv" in nk or nk.endswith("voltage"))
            ):
                f = _as_float(val)
                if f is not None and f > 400:  # likely volts
                    f = f / 1000.0
                hit = _sane_kv(f)
                if hit is not None:
                    return hit, f"json:{path}"
            if nk in ("vtratio", "ptratio", "voltagetransformerratio") or (
                "vt" in nk and "ratio" in nk
            ):
                if isinstance(val, str):
                    m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*[/:]\s*([0-9]+(?:\.[0-9]+)?)", val)
                    if m:
                        pri = float(m.group(1))
                        hit = _kv_from_vt_primary_volts(pri)
                        if hit is not None:
                            return hit, f"json_vt_ratio:{path}"
                f = _as_float(val)
                if f is not None:
                    hit = _kv_from_vt_primary_volts(f)
                    if hit is not None:
                        return hit, f"json_vt_primary:{path}"

    # 2) Settings / report text
    for text in texts or []:
        if not text:
            continue
        for pat in _KV_TEXT_PATTERNS[:2]:  # explicit nominal/system lines first
            m = pat.search(text)
            if m:
                hit = _sane_kv(float(m.group(1)))
                if hit is not None:
                    return hit, "settings_text:nominal_voltage"
        m = _VT_RATIO_RE.search(text) or _VT_RATIO_BARE.search(text)
        if m:
            hit = _kv_from_vt_primary_volts(float(m.group(1)))
            if hit is not None:
                return hit, "settings_text:vt_ratio"

    # 3) Filename / station name (…132kV… / …132KV…)
    for label, src in (
        *[(n, "filename") for n in (filenames or [])],
        *([(station, "station")] if station else []),
    ):
        if not label:
            continue
        m = re.search(r"(?i)(?:^|[^0-9])([0-9]{2,3}(?:\.[0-9]+)?)\s*k\s*v(?:[^a-z]|$)", label)
        if m:
            hit = _sane_kv(float(m.group(1)))
            if hit is not None:
                return hit, f"{src}:kv_token"

    # 4) Any remaining bare "NNN kV" in concatenated texts (last resort)
    for text in texts or []:
        if not text:
            continue
        m = _KV_TEXT_PATTERNS[2].search(text)
        if m:
            hit = _sane_kv(float(m.group(1)))
            if hit is not None:
                return hit, "text:kv_token"

    return None, None
