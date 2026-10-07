"""MiCOM / Schneider Courier ``.set`` parser (deterministic).

Courier setting files are binary with embedded ASCII labels. This module
extracts:

- metadata (model, plant, frequency, active group)
- CT / VT ratios
- protection function enable / curve / pickup / delay for common OC / EF / BF

Never invents missing values — unmapped cells stay absent.
"""

from __future__ import annotations

import re
import struct
from typing import Any, Optional


def is_micom_courier_set(data: bytes, filename: str = "") -> bool:
    name = (filename or "").lower()
    head = data[:200].decode("latin-1", errors="ignore")
    if "APP: Courier" in head and "TYPE: Setting" in head:
        return True
    if name.endswith(".set") and ("MiCOM" in head or "Courier" in head):
        return True
    return False


def _u16_le(b: bytes, off: int = 0) -> int:
    return struct.unpack_from("<H", b, off)[0]


def _decode_k_values(blob: bytes, start: int, limit: int = 80) -> list[float]:
    """After ``%k``, Courier stores ``,\\x04 <u16><scale><cell>`` groups.

    Scale byte encodes decimal places as ``decimals = 0x7E - scale``
    (clamped to 0..6). Groups are typically value / min / max / step.
    """
    j = blob.find(b"%k", start, start + 48)
    if j < 0:
        return []
    pos = j + 2
    end = min(len(blob), j + limit)
    out: list[float] = []
    while pos + 6 <= end and len(out) < 6:
        if blob[pos] == 0x2C and blob[pos + 1] in (3, 4, 5, 6):
            raw = _u16_le(blob, pos + 2)
            scale_byte = blob[pos + 4]
            decimals = 0x7E - scale_byte
            if decimals < 0:
                decimals = 0
            if decimals > 6:
                decimals = 6
            out.append(raw / (10**decimals))
            pos += 6
        else:
            pos += 1
    return out


def _find_label_value(blob: bytes, label: str) -> Optional[float]:
    lab = label.encode("ascii", errors="ignore")
    i = blob.find(lab)
    if i < 0:
        return None
    nums = _decode_k_values(blob, i)
    if not nums:
        return None
    return nums[0]


def _find_u_value(blob: bytes, label: str) -> Optional[float]:
    """Decode ``%u … $\\x02 <u16 LE>`` cells (e.g. Frequency)."""
    lab = label.encode("ascii", errors="ignore")
    i = blob.find(lab)
    if i < 0:
        return None
    region = blob[i : i + 64]
    j = region.find(b"%u")
    if j < 0:
        return None
    k = region.find(b"$\x02", j, j + 40)
    if k < 0 or k + 4 > len(region):
        return None
    return float(_u16_le(region, k + 2))


def _enum_selection(blob: bytes, label: bytes) -> Optional[str]:
    """Decode ``%sP`` selected index into option string (Enabled/Disabled/curve…)."""
    i = blob.find(label)
    if i < 0:
        return None
    j = blob.find(b"%sP", i, i + 40)
    if j < 0:
        return None
    # Selected index: %sP \x02 <u16 LE>
    if j + 5 >= len(blob) or blob[j + 3] != 0x02:
        return None
    idx = _u16_le(blob, j + 4)
    # Option strings follow after 0xff 0x00 markers or after $ blocks
    k = blob.find(b"\xff\x00\xff\x00\xff\x00", j, j + 80)
    opt_start = k + 6 if k >= 0 else j + 20
    region = blob[opt_start : opt_start + 400]
    parts = region.split(b"\x00")
    options: list[str] = []
    for p in parts:
        if not p:
            continue
        if not all(32 <= b < 127 for b in p):
            if options:
                break
            continue
        s = p.decode("ascii", errors="ignore").strip()
        if len(s) >= 2:
            options.append(s)
        if len(options) >= 16:
            break
    if not options:
        return None
    if 0 <= idx < len(options):
        return options[idx]
    return None


def _ascii_field(blob: bytes, label: str, max_len: int = 48) -> Optional[str]:
    lab = label.encode("ascii", errors="ignore")
    i = blob.find(lab)
    if i < 0:
        return None
    region = blob[i : i + 120]
    j = region.find(b"%s")
    if j >= 0:
        pos = j + 2
        # Length-prefixed: %s \x18 <n> <n bytes>
        if pos + 2 <= len(region) and region[pos] == 0x18:
            n = region[pos + 1]
            raw = region[pos + 2 : pos + 2 + n]
            text = raw.split(b"$")[0].decode("ascii", errors="ignore").strip()
            text = re.sub(r"[\x00-\x1f]+", " ", text).strip()
            if text:
                return text[:max_len]
        m = re.search(rb"%s.{0,8}([A-Za-z0-9][ -~]{1," + str(max_len).encode() + rb"})", region)
        if m:
            text = m.group(1).decode("ascii", errors="ignore").split("$")[0].strip()
            if text and not text.startswith("%"):
                return text[:max_len]
    # Fallback: first long printable after label
    asc = "".join(chr(b) if 32 <= b < 127 else "\n" for b in region)
    for part in asc.split("\n"):
        part = part.strip().strip("$").strip()
        if label.lower() in part.lower():
            continue
        if len(part) >= 3 and not part.startswith("%"):
            return part[:max_len]
    return None


def parse_micom_courier_set(data: bytes, *, filename: str = "settings.set") -> dict[str, Any]:
    """Parse MiCOM Courier ``.set`` into settings_ingest-compatible payload."""
    if not is_micom_courier_set(data, filename):
        return {
            "status": "NOT_CALCULABLE",
            "vendor": "SCHNEIDER",
            "reason": "Not a MiCOM Courier TYPE: Setting file",
            "raw": {},
            "mapped": {},
            "common": {},
            "param_count": 0,
            "raw_keys": [],
        }

    head = data[:400].decode("latin-1", errors="ignore")
    model = None
    m = re.search(r"MODEL:\s*(\S+)", head, re.I)
    if m:
        model = m.group(1).strip()
    plant = _ascii_field(data, "Plant Reference") or _ascii_field(data, "Description")
    freq = _find_u_value(data, "Frequency")
    if freq is None:
        freq = _find_label_value(data, "Frequency")

    raw: dict[str, Any] = {
        "vendor_format": "MICOM_COURIER_SET",
        "filename": filename,
    }
    if model:
        raw["model"] = model
    if plant:
        raw["plant_reference"] = plant
    if freq is not None:
        raw["frequency_hz"] = freq

    # CT / VT
    ct_pri = _find_label_value(data, "Phase CT Primary")
    ct_sec = _find_label_value(data, "Phase CT Sec")
    vt_pri = _find_label_value(data, "Main VT Primary")
    vt_sec = _find_label_value(data, "Main VT Sec")
    ef_ct_pri = _find_label_value(data, "E/F CT Primary")
    ef_ct_sec = _find_label_value(data, "E/F CT Sec")
    ct_vt: dict[str, Any] = {}
    if ct_pri is not None and ct_sec is not None and ct_sec > 0:
        ct_vt["ct_ratio"] = float(ct_pri) / float(ct_sec)
        ct_vt["ct_primary_a"] = ct_pri
        ct_vt["ct_secondary_a"] = ct_sec
        raw["phase_ct_primary"] = ct_pri
        raw["phase_ct_secondary"] = ct_sec
    if vt_pri is not None and vt_sec is not None and vt_sec > 0:
        ct_vt["vt_ratio"] = float(vt_pri) / float(vt_sec)
        ct_vt["vt_primary_v"] = vt_pri
        ct_vt["vt_secondary_v"] = vt_sec
        raw["main_vt_primary"] = vt_pri
        raw["main_vt_secondary"] = vt_sec
    if ef_ct_pri is not None:
        raw["ef_ct_primary"] = ef_ct_pri
    if ef_ct_sec is not None:
        raw["ef_ct_secondary"] = ef_ct_sec

    protection: dict[str, dict[str, Any]] = {}

    # Configuration enables
    oc_en = _enum_selection(data, b"Overcurrent")
    ef1_en = _enum_selection(data, b"Earth Fault 1")
    cb_fail_en = _enum_selection(data, b"CB Fail")

    def _enabled(s: Optional[str]) -> Optional[bool]:
        if s is None:
            return None
        u = s.strip().lower()
        if u in ("enabled", "enable", "on", "yes"):
            return True
        if u in ("disabled", "disable", "off", "no"):
            return False
        return None

    # Phase OC stages I>1 … I>2 → 51 / 50
    i1_fn = _enum_selection(data, b"I>1 Function")
    i1_pu = _find_label_value(data, "I>1 Current Set")
    i1_td = _find_label_value(data, "I>1 Time Delay")
    i1_tms = _find_label_value(data, "I>1 TMS")
    if i1_fn or i1_pu is not None:
        block51: dict[str, Any] = {}
        en = _enabled(oc_en)
        if en is not None:
            block51["enabled"] = en and (i1_fn not in (None, "Disabled"))
        elif i1_fn and i1_fn != "Disabled":
            block51["enabled"] = True
        if i1_pu is not None:
            block51["pickup_current"] = i1_pu
            raw["i1_current_set_a"] = i1_pu
        if i1_td is not None:
            block51["time_delay_s"] = i1_td
        if i1_tms is not None:
            block51["time_dial"] = i1_tms
        if i1_fn and i1_fn != "Disabled":
            block51["curve"] = i1_fn
            raw["i1_function"] = i1_fn
        if block51:
            protection["51"] = block51

    i2_fn = _enum_selection(data, b"I>2 Function")
    i2_pu = _find_label_value(data, "I>2 Current Set")
    if (i2_fn and i2_fn != "Disabled") or i2_pu is not None:
        block50: dict[str, Any] = {}
        if i2_fn and i2_fn != "Disabled":
            block50["enabled"] = True
            block50["curve"] = i2_fn
        if i2_pu is not None:
            block50["pickup_current"] = i2_pu
            raw["i2_current_set_a"] = i2_pu
        if block50:
            protection["50"] = block50

    # Earth fault IN1>
    in1_pu = _find_label_value(data, "IN1>1 Current")
    in1_fn = _enum_selection(data, b"IN1>1 Function")
    if in1_pu is not None or (ef1_en and _enabled(ef1_en)):
        block51n: dict[str, Any] = {}
        en = _enabled(ef1_en)
        if en is not None:
            block51n["enabled"] = en
        if in1_pu is not None:
            block51n["pickup_current"] = in1_pu
            raw["in1_current_set_a"] = in1_pu
        if in1_fn and in1_fn != "Disabled":
            block51n["curve"] = in1_fn
        if block51n:
            protection["51N"] = block51n

    # CB Fail
    if cb_fail_en is not None:
        en = _enabled(cb_fail_en)
        if en is not None:
            protection["50BF"] = {"enabled": en}
            raw["cb_fail"] = cb_fail_en

    # Diff (when present on transformer products)
    for lab in (b"Diff Protection", b"Differential", b"Biased Diff"):
        sel = _enum_selection(data, lab)
        if sel is not None:
            en = _enabled(sel)
            if en is not None:
                protection.setdefault("87T", {})["enabled"] = en
                raw["diff_protection"] = sel
            break

    common: dict[str, Any] = {}
    if "51" in protection and "pickup_current" in protection["51"]:
        common["pickup_a"] = protection["51"]["pickup_current"]
        common["pickup_current"] = protection["51"]["pickup_current"]
    if "51" in protection and "time_dial" in protection["51"]:
        common["time_dial"] = protection["51"]["time_dial"]
    if "ct_ratio" in ct_vt:
        common["ct_ratio"] = ct_vt["ct_ratio"]
    if "vt_ratio" in ct_vt:
        common["vt_ratio"] = ct_vt["vt_ratio"]

    mapped = {
        "protection": protection,
        "line": {},
        "ct_vt": ct_vt,
        "device": {"model": model, "plant_reference": plant, "frequency_hz": freq},
    }

    param_count = len(raw) + sum(len(v) for v in protection.values()) + len(ct_vt)
    return {
        "status": "OK" if param_count else "NOT_CALCULABLE",
        "vendor": "SCHNEIDER",
        "filename": filename,
        "param_count": param_count,
        "mapped": mapped,
        "common": common,
        "raw": raw,
        "raw_keys": sorted(raw.keys()),
        "reason": None if param_count else "No MiCOM Courier settings decoded",
    }
