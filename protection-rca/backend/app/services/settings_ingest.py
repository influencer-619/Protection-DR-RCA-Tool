"""Vendor settings ingest helpers (deterministic parsers — no GenAI).

Supports common export shapes used in industry DR tools:
  - JSON (Protection RCA / generic)
  - KEY=VALUE / KEY: VALUE text dumps
  - SEL SET_ALL.TXT / SET_*.TXT style sections
  - ABB PCM600 / Siemens / GE / Schneider text+CSV
  - Basic XRIO / settings XML parameter extraction
"""

from __future__ import annotations

import csv
import io
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Optional


def _coerce_val(val: str) -> Any:
    v = (val or "").strip().strip('"').strip("'")
    if not v:
        return v
    try:
        if "." in v or "e" in v.lower():
            return float(v)
        return int(v)
    except ValueError:
        pass
    low = v.lower()
    if low in ("true", "yes", "on", "enabled", "y"):
        return True
    if low in ("false", "no", "off", "disabled", "n"):
        return False
    return v


def _flatten_kv_lines(text: str) -> dict[str, Any]:
    """Parse simple KEY=VALUE or KEY: VALUE lines from relay setting dumps."""
    out: dict[str, Any] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("//") or line.startswith(";"):
            continue
        # Skip section headers like [SET_1]
        if line.startswith("[") and line.endswith("]"):
            continue
        if "=" in line:
            k, _, v = line.partition("=")
        elif ":" in line and not re.match(r"^\d{1,2}:\d{2}", line):
            k, _, v = line.partition(":")
        else:
            continue
        key = k.strip().replace(" ", "_")
        if not key:
            continue
        out[key.lower()] = _coerce_val(v)
        # Keep original-case alias for SEL-style tokens
        out[key] = _coerce_val(v)
    return out


def parse_sel_set_all(text: str) -> dict[str, Any]:
    """Parse SEL SET_ALL / SET_n.TXT style INI-ish configuration."""
    out: dict[str, Any] = {}
    section = "GENERAL"
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        m = re.match(r"^\[([^\]]+)\]$", line)
        if m:
            section = m.group(1).strip().upper()
            continue
        if "=" not in line:
            continue
        k, _, v = line.partition("=")
        key = k.strip()
        if not key:
            continue
        val = _coerce_val(v)
        out[key.lower()] = val
        out[key] = val
        out[f"{section}.{key}".lower()] = val
    return out


def parse_settings_csv(text: str) -> dict[str, Any]:
    """Parse PCM600 / generic settings CSV (parameter,value or name,value)."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return _flatten_kv_lines(text)
    fields = {(h or "").strip().lower(): h for h in reader.fieldnames}
    name_key = (
        fields.get("parameter")
        or fields.get("param")
        or fields.get("name")
        or fields.get("setting")
        or fields.get("key")
    )
    val_key = fields.get("value") or fields.get("val") or fields.get("settingvalue")
    if not name_key or not val_key:
        # Fallback: first two columns
        cols = list(reader.fieldnames)
        if len(cols) < 2:
            return {}
        name_key, val_key = cols[0], cols[1]
        reader = csv.DictReader(io.StringIO(text))
    out: dict[str, Any] = {}
    for row in reader:
        k = str(row.get(name_key) or "").strip()
        v = str(row.get(val_key) or "").strip()
        if not k or v in ("", "-"):
            continue
        out[k.lower().replace(" ", "_")] = _coerce_val(v)
        out[k] = _coerce_val(v)
    return out


def parse_settings_xml(text: str) -> dict[str, Any]:
    """Extract Name/Value (or similar) pairs from XRIO / settings XML."""
    out: dict[str, Any] = {}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return out

    def _walk(node: ET.Element) -> None:
        tag = (node.tag or "").split("}")[-1].lower()
        attrs = {k.lower(): v for k, v in node.attrib.items()}
        name = (
            attrs.get("name")
            or attrs.get("id")
            or attrs.get("parameter")
            or attrs.get("pathname")
        )
        val = attrs.get("value") or attrs.get("val")
        if name and val is not None and val != "":
            out[str(name).lower().replace(" ", "_")] = _coerce_val(str(val))
            out[str(name)] = _coerce_val(str(val))
        # Child text pattern: <Parameter><Name>x</Name><Value>y</Value>
        if tag in ("parameter", "setting", "param"):
            child_name = None
            child_val = None
            for ch in node:
                ct = (ch.tag or "").split("}")[-1].lower()
                if ct in ("name", "id", "pathname") and (ch.text or "").strip():
                    child_name = ch.text.strip()
                if ct in ("value", "val") and ch.text is not None:
                    child_val = ch.text.strip()
            if child_name and child_val is not None:
                out[child_name.lower().replace(" ", "_")] = _coerce_val(child_val)
                out[child_name] = _coerce_val(child_val)
        for ch in node:
            _walk(ch)

    _walk(root)
    return out


def detect_vendor(filename: str, text_sample: str = "") -> str:
    n = Path(filename or "").name.lower()
    s = (text_sample or "")[:8000].lower()
    # Prefer strong markers before short tokens like "ge" / "ur"
    if (
        "schweitzer" in s
        or "sel-" in s
        or re.search(r"\bfid\s*=\s*sel", s)
        or "[set_" in s
        or "set_all" in n
        or n.startswith("set_")
        or "acselerator" in n
        or re.search(r"(^|[_\-.])sel([_\-.]|$)", n)
    ):
        return "SEL"
    if "abb" in n or "pcm600" in n or "ref615" in s or "relion" in s or "xrio" in n:
        return "ABB"
    if "siemens" in n or "digsi" in n or "7sa" in s or "siprotec" in s:
        return "SIEMENS"
    if (
        "schneider" in n
        or "sepam" in s
        or "micom" in s
        or "easergy" in s
        or "ecopact" in s
    ):
        return "SCHNEIDER"
    if (
        "enervista" in n
        or "multilin" in s
        or "ge multilin" in s
        or re.search(r"(^|[_\-.])ge([_\-.]|$)", n)
        or re.search(r"(^|[_\-.])ur([_\-.]|$)", n)
    ):
        return "GE"
    if n.endswith(".json") or text_sample.strip().startswith("{"):
        return "JSON"
    if n.endswith((".xrio", ".xml")) or "<" in text_sample[:200]:
        return "XML"
    return "GENERIC"


# SEL mnemonic → (element, canonical_param)
_SEL_MAP: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"^E?51[SP]?P$", re.I), "51", "pickup_current"),
    (re.compile(r"^51[SP]?TD$", re.I), "51", "time_dial"),
    (re.compile(r"^51[SP]?C$", re.I), "51", "curve"),
    (re.compile(r"^E51", re.I), "51", "enabled"),
    (re.compile(r"^50[SP]?P?\d*P$", re.I), "50", "pickup_current"),
    (re.compile(r"^E50", re.I), "50", "enabled"),
    (re.compile(r"^Z1MAG$|^Z1P$", re.I), "21", "zone1_reach"),
    (re.compile(r"^Z1ANG$", re.I), "21", "zone1_angle"),
    (re.compile(r"^EZ1$|^E21", re.I), "21", "enabled"),
    (re.compile(r"^67[SP]?P$", re.I), "67", "pickup_current"),
    (re.compile(r"^E67", re.I), "67", "enabled"),
    (re.compile(r"^87[LBTG]?P$|^87LAP$", re.I), "87L", "pickup_current"),
    (re.compile(r"^E87", re.I), "87L", "enabled"),
    (re.compile(r"^50BF|BFDLY|BFTD", re.I), "50BF", "bf_timer_s"),
    (re.compile(r"^CTR$|^CTRN$", re.I), "GENERAL", "ct_ratio"),
    (re.compile(r"^PTR$|^PTRN$|^VTR$", re.I), "GENERAL", "vt_ratio"),
    (re.compile(r"^LL$|^LINELEN", re.I), "GENERAL", "length_km"),
]


def map_sel_mnemonics(flat: dict[str, Any]) -> dict[str, Any]:
    """Map SEL mnemonics into protection element blocks."""
    protection: dict[str, dict[str, Any]] = {}
    line: dict[str, Any] = {}
    ct_vt: dict[str, Any] = {}
    for key, val in flat.items():
        if "." in str(key) and not str(key).upper().startswith("SET"):
            # Prefer bare mnemonic keys
            continue
        k = str(key)
        for pat, element, param in _SEL_MAP:
            if pat.match(k):
                if element == "GENERAL":
                    if param in ("ct_ratio", "vt_ratio"):
                        ct_vt[param] = val
                    elif param == "length_km":
                        line[param] = val
                else:
                    block = protection.setdefault(element, {})
                    if param == "enabled":
                        block["enabled"] = bool(val) if isinstance(val, bool) else str(val).upper() in (
                            "Y",
                            "YES",
                            "TRUE",
                            "1",
                            "ON",
                        )
                    else:
                        block[param] = val
                break
    return {"protection": protection, "line": line, "ct_vt": ct_vt}


def map_common_protection_params(flat: dict[str, Any]) -> dict[str, Any]:
    """Map common vendor keys into Protection RCA setting blocks."""
    aliases = {
        "pickup_a": (
            "pickup",
            "pickup_a",
            "i_pickup",
            "oc_pickup",
            "51_pickup",
            "ip",
            "id_min",
            "pickup_current",
        ),
        "time_dial": ("time_dial", "td", "tms", "time_multiplier", "tds"),
        "curve": ("curve", "characteristic", "iec_curve", "ansi_curve"),
        "enabled": ("enabled", "function_enabled", "on"),
        "bf_timer_s": ("bf_timer", "bf_timer_s", "50bf_timer", "breaker_fail_timer"),
        "slope": ("slope", "k", "percent_slope", "bias_slope"),
        "mta_deg": ("mta", "mta_deg", "max_torque_angle", "rca"),
        "ct_ratio": ("ct_ratio", "ctr", "ct", "ctrn"),
        "vt_ratio": ("vt_ratio", "vtr", "pt_ratio", "vt", "ptr", "ptrn"),
        "length_km": ("length_km", "line_length", "length", "ll"),
        "z1_r": ("z1_r", "r1", "positive_sequence_r_ohm_per_km"),
        "z1_x": ("z1_x", "x1", "positive_sequence_x_ohm_per_km"),
        "zone1_reach": ("zone1_reach", "z1mag", "z1_reach", "zone1_reach_ohm"),
    }
    mapped: dict[str, Any] = {}
    lower = {str(k).lower(): v for k, v in flat.items()}
    for target, keys in aliases.items():
        for k in keys:
            if k in lower and lower[k] not in (None, ""):
                mapped[target] = lower[k]
                break
    return mapped


def ingest_settings_bytes(
    data: bytes,
    *,
    filename: str = "settings.txt",
) -> dict[str, Any]:
    """
    Parse a settings file into a normalized payload.

    Never invents missing parameters — unmapped keys stay in ``raw``.
    Binary .rdb (SEL AcSELerator project) is not fully decoded here.
    """
    name_l = Path(filename).name.lower()
    if name_l.endswith(".rdb"):
        from app.services.vendor_formats import extract_sel_rdb_text

        extracted = extract_sel_rdb_text(data)
        if extracted.get("status") != "OK" or not extracted.get("text"):
            return {
                "status": "NOT_CALCULABLE",
                "vendor": "SEL",
                "reason": extracted.get("reason")
                or "SEL .rdb could not be decoded — export SET_ALL.TXT",
                "filename": Path(filename).name,
                "raw": {},
                "mapped": {},
                "common": {},
                "param_count": 0,
                "raw_keys": [],
                "streams": extracted.get("streams") or [],
            }
        # Re-enter as SET_ALL text
        return ingest_settings_bytes(
            extracted["text"].encode("utf-8", errors="replace"),
            filename="SET_ALL.TXT",
        )

    text = ""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = data.decode("latin-1")
        except Exception:  # noqa: BLE001
            return {
                "status": "NOT_CALCULABLE",
                "vendor": "UNKNOWN",
                "reason": "Unable to decode settings file as text",
                "raw": {},
                "mapped": {},
                "common": {},
                "param_count": 0,
                "raw_keys": [],
            }

    vendor = detect_vendor(filename, text)
    raw: dict[str, Any] = {}

    if vendor == "JSON" or name_l.endswith(".json"):
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                raw = parsed
            else:
                raw = {"_root": parsed}
        except json.JSONDecodeError:
            raw = _flatten_kv_lines(text)
            vendor = detect_vendor(filename, text) if vendor == "JSON" else vendor
    elif name_l.endswith((".xml", ".xrio")) or vendor == "XML" or text.lstrip().startswith("<"):
        raw = parse_settings_xml(text)
        if not raw:
            raw = _flatten_kv_lines(text)
        if vendor == "GENERIC":
            vendor = "XML"
    elif name_l.endswith(".csv"):
        raw = parse_settings_csv(text)
    elif vendor == "SEL" or "[SET_" in text.upper() or "FID=" in text.upper():
        raw = parse_sel_set_all(text)
        if vendor == "GENERIC":
            vendor = "SEL"
    else:
        raw = _flatten_kv_lines(text)

    # Nested protection blocks often already normalized
    if isinstance(raw, dict) and (
        "line" in raw or "ct_vt" in raw or "protection" in raw or "elements" in raw
    ):
        mapped = dict(raw)
        # Prefer elements → protection
        if "elements" in mapped and "protection" not in mapped:
            mapped["protection"] = mapped["elements"]
        common = map_common_protection_params(_flatten_dict(raw))
    else:
        common = map_common_protection_params(raw)
        mapped = {
            "protection": {
                "51": {
                    k: common[k]
                    for k in ("pickup_a", "time_dial", "curve", "enabled", "pickup_current")
                    if k in common
                },
                "87": {k: common[k] for k in ("slope", "pickup_a", "enabled") if k in common},
                "67": {k: common[k] for k in ("mta_deg", "enabled") if k in common},
                "50BF": {k: common[k] for k in ("bf_timer_s", "enabled") if k in common},
                "21": {
                    k: common[k]
                    for k in ("zone1_reach", "enabled")
                    if k in common
                },
            },
            "line": {
                k: common[k]
                for k in ("length_km", "z1_r", "z1_x")
                if k in common
            },
            "ct_vt": {k: common[k] for k in ("ct_ratio", "vt_ratio") if k in common},
        }
        # Drop empty element blocks
        mapped["protection"] = {k: v for k, v in mapped["protection"].items() if v}
        line = mapped["line"]
        if "z1_r" in line and "z1_x" in line:
            line["positive_sequence_r_ohm_per_km"] = line.pop("z1_r")
            line["positive_sequence_x_ohm_per_km"] = line.pop("z1_x")
        if "zone1_reach" in common:
            mapped["protection"].setdefault("21", {})["zone1_reach"] = common["zone1_reach"]
            if "pickup_a" in mapped["protection"].get("51", {}):
                mapped["protection"]["51"]["pickup_current"] = mapped["protection"]["51"].pop(
                    "pickup_a"
                )

        if vendor == "SEL":
            sel_mapped = map_sel_mnemonics(raw)
            for el, block in (sel_mapped.get("protection") or {}).items():
                cur = dict(mapped["protection"].get(el) or {})
                cur.update(block)
                mapped["protection"][el] = cur
            for k, v in (sel_mapped.get("line") or {}).items():
                mapped["line"].setdefault(k, v)
            for k, v in (sel_mapped.get("ct_vt") or {}).items():
                mapped["ct_vt"].setdefault(k, v)

    return {
        "status": "OK" if _flatten_dict(raw) else "NOT_CALCULABLE",
        "vendor": vendor,
        "filename": Path(filename).name,
        "param_count": len(_flatten_dict(raw)),
        "mapped": mapped,
        "common": common,
        "raw_keys": sorted(_flatten_dict(raw).keys())[:200],
        "reason": None if _flatten_dict(raw) else "No recognizable setting parameters",
    }


def _flatten_dict(d: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else str(k)
        if isinstance(v, dict):
            out.update(_flatten_dict(v, key))
        else:
            out[key] = v
    return out


def merge_ingested_into_event_extra(extra: dict[str, Any], ingested: dict[str, Any]) -> dict[str, Any]:
    """Merge ingest result into event.extra without inventing values."""
    out = dict(extra)
    mapped = ingested.get("mapped") or {}
    if isinstance(mapped.get("line"), dict) and mapped["line"]:
        line = dict(out.get("line_params") or {})
        line.update({k: v for k, v in mapped["line"].items() if v is not None})
        out["line_params"] = line
    if isinstance(mapped.get("ct_vt"), dict) and mapped["ct_vt"]:
        ct = dict(out.get("ct_vt") or {})
        ct.update({k: v for k, v in mapped["ct_vt"].items() if v is not None})
        out["ct_vt"] = ct
    if isinstance(mapped.get("protection"), dict) and mapped["protection"]:
        prot = dict(out.get("relay_settings") or {})
        for el, block in mapped["protection"].items():
            if isinstance(block, dict) and block:
                cur = dict(prot.get(el) or {})
                cur.update(block)
                prot[el] = cur
        out["relay_settings"] = prot
    out["settings_ingest"] = {
        "vendor": ingested.get("vendor"),
        "filename": ingested.get("filename"),
        "param_count": ingested.get("param_count"),
        "status": ingested.get("status"),
        "reason": ingested.get("reason"),
    }
    out["setting_source"] = out.get("setting_source") or f"VENDOR_{ingested.get('vendor', 'GENERIC')}"
    return out


def setting_records_from_ingested(
    ingested: dict[str, Any],
) -> tuple[dict[str, Any], list[Any]]:
    """Convert ingest mapped.protection into SettingRecord list for the analysis pipeline."""
    from settings.hierarchy.resolver import SettingRecord, SettingSource
    from app.services.settings_package import apply_upload_auto_approval, map_setting_source

    mapped = ingested.get("mapped") or {}
    protection = mapped.get("protection") if isinstance(mapped.get("protection"), dict) else {}
    vendor = str(ingested.get("vendor") or "GENERIC")
    fname = str(ingested.get("filename") or "settings")
    meta = apply_upload_auto_approval(
        {
            "source": f"VENDOR_{vendor}",
            "version": "UPLOADED",
            "group": "Base",
            "verified": False,
            "approval_status": "NOT VERIFIED",
        }
    )
    records: list[Any] = []
    flat: dict[str, Any] = {
        "setting_source": str(meta["source"]),
        "setting_version": str(meta["version"]),
        "setting_group": str(meta["group"]),
        "active_group": str(meta["group"]),
        "version": str(meta["version"]),
        "active_setting_group_verified": bool(meta["verified"]),
        "approval_status": str(meta["approval_status"]),
        "_source_file": fname,
        "_meta": meta,
    }
    src = map_setting_source(str(meta["source"]))
    i = 0
    for el, block in protection.items():
        if not isinstance(block, dict):
            continue
        for param, value in block.items():
            if isinstance(value, (dict, list)):
                continue
            enabled_flag: Optional[bool] = None
            if str(param).lower() == "enabled" and isinstance(value, bool):
                enabled_flag = value
            # Normalize pickup_a → pickup_current
            p = "pickup_current" if str(param).lower() in ("pickup_a", "pickup") else str(param)
            records.append(
                SettingRecord(
                    setting_id=f"vendor-{el}-{p}-{i}",
                    relay_id="UPLOADED",
                    setting_group=str(meta["group"]),
                    parameter=p,
                    value=value,
                    unit="",
                    enabled=enabled_flag if enabled_flag is not None else True,
                    version=str(meta["version"]),
                    source=src if src else SettingSource.RELAY_CONFIGURATION,
                    approval_status=str(meta["approval_status"]),
                    verified=bool(meta["verified"]),
                    element=str(el).upper(),
                )
            )
            flat[f"{el}.{p}"] = value
            flat.setdefault(p, value)
            i += 1
    # Surface line / ct_vt into flat for param_detect consumers
    for section in ("line", "ct_vt"):
        block = mapped.get(section)
        if isinstance(block, dict):
            for k, v in block.items():
                flat[k] = v
    return flat, records
