"""Normalize uploaded relay-settings packages into SettingRecord rows.

Supports nested JSON used by Protection RCA fixtures:
  - elements / protection_elements maps
  - setting_reference / setting_group / setting_version metadata
Never invents values — only reshapes what is present in the file.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PARAM_ALIASES: dict[str, str] = {
    "pickup_a": "pickup_current",
    "pickup_a_primary": "pickup_current",
    "i_pickup": "pickup_current",
    "pickup": "pickup_current",
    "time_multiplier": "time_dial",
    "tms": "time_dial",
    "tds": "time_dial",
    "zone1_reach_ohm": "zone1_reach",
    "zone1_reach_percent": "zone1_reach",
    "curve_type": "curve",
}

_META_KEYS = {
    "event_id",
    "relay",
    "asset",
    "schema",
    "setting_source",
    "setting_version",
    "setting_group",
    "active_setting_group_verified",
    "active_group",
    "version",
    "approval_status",
    "setting_reference",
    "setting_approval",
    "ct_vt",
    "line",
    "elements",
    "protection_elements",
    "meta",
    "metadata",
    "comment",
    "comments",
    "verification_note",
}

_ELEMENT_PREFIXES = (
    "87RGF",
    "50BF",
    "87G",
    "87T",
    "87L",
    "87B",
    "50N",
    "51N",
    "67N",
    "67P",
    "50P",
    "51P",
    "21G",
    "21P",
    "32R",
    "81U",
    "81O",
    "81R",
    "50",
    "51",
    "21",
    "67",
    "87",
    "32",
    "46",
    "68",
    "78",
    "27",
    "59",
    "81",
    "79",
    "86",
    "25",
)


def canonical_param(name: str) -> str:
    key = str(name).strip()
    return _PARAM_ALIASES.get(key.lower(), key)


def looks_like_settings_json(name: str, data: dict[str, Any]) -> bool:
    n = (name or "").lower()
    if any(x in n for x in ("setting", "relay", "param")):
        return True
    if any(
        k in data
        for k in (
            "elements",
            "protection_elements",
            "setting_reference",
            "setting_group",
            "setting_version",
            "setting_source",
        )
    ):
        return True
    keys = {str(k).lower() for k in data}
    return bool(
        keys
        & {
            "pickup_current",
            "pickup_a",
            "pickup_a_primary",
            "time_dial",
            "zone1_reach",
            "zone1_reach_ohm",
        }
    )


def _auto_approve_uploads_enabled() -> bool:
    try:
        from app.core.config import get_settings

        return bool(get_settings().auto_approve_uploaded_settings)
    except Exception:  # noqa: BLE001
        return True


def apply_upload_auto_approval(meta: dict[str, Any]) -> dict[str, Any]:
    """
    Treat uploaded setting packages as APPROVED + active-group VERIFIED.

    Skips only when the package explicitly marks rejection / draft / pending review.
    """
    out = dict(meta or {})
    if not _auto_approve_uploads_enabled():
        return out
    approval = str(out.get("approval_status") or "").upper()
    if approval in ("REJECTED", "DRAFT", "PENDING", "PENDING_REVIEW", "NOT_APPROVED"):
        return out
    out["approval_status"] = "APPROVED"
    out["verified"] = True
    src = str(out.get("source") or "")
    if "APPROVED" not in src.upper() and src.upper() in (
        "",
        "RELAY_CONFIGURATION",
        "UPLOADED",
        "EVENT_SPECIFIC",
        "EVENT_SPECIFIC_ACTIVE",
    ):
        out["source"] = "APPROVED_RELAY_BASE"
    note = str(out.get("verification_note") or "").strip()
    if not note:
        out["verification_note"] = "Auto-approved on upload (auto_approve_uploaded_settings)"
    return out


def extract_settings_meta(data: dict[str, Any]) -> dict[str, Any]:
    ref = data.get("setting_reference") if isinstance(data.get("setting_reference"), dict) else {}
    source = (
        data.get("setting_source")
        or ref.get("source")
        or data.get("source")
        or "RELAY_CONFIGURATION"
    )
    version = (
        data.get("setting_version")
        or ref.get("version")
        or data.get("version")
        or "UPLOADED"
    )
    group = (
        data.get("setting_group")
        or ref.get("group")
        or data.get("active_group")
        or "Base"
    )
    verified_raw = data.get("active_setting_group_verified")
    if verified_raw is None:
        verified_raw = ref.get("active_setting_group_verified")
    verified = bool(verified_raw) if verified_raw is not None else False
    approval = data.get("approval_status") or ref.get("approval_status")
    if not approval:
        approval = "APPROVED" if "APPROVED" in str(source).upper() else "NOT VERIFIED"
    # Approved base settings: the group in the package is the approved baseline → VERIFIED
    if "APPROVED" in str(source).upper() and "APPROVED" in str(approval).upper():
        verified = True
    note = (
        data.get("verification_note")
        or ref.get("verification_note")
        or ""
    )
    meta = {
        "source": str(source),
        "version": str(version),
        "group": str(group),
        "verified": verified,
        "approval_status": str(approval),
        "verification_note": str(note) if note else "",
    }
    return apply_upload_auto_approval(meta)


def flatten_element_params(elements: dict[str, Any]) -> list[tuple[str, str, Any]]:
    rows: list[tuple[str, str, Any]] = []
    for el_code, params in elements.items():
        code = str(el_code).strip()
        if not code:
            continue
        if not isinstance(params, dict):
            rows.append((code, "enabled", bool(params)))
            continue
        for raw_key, val in params.items():
            if isinstance(val, (dict, list)):
                continue
            param = canonical_param(str(raw_key))
            rows.append((code, param, val))
            if param != str(raw_key):
                rows.append((code, str(raw_key), val))
    return rows


def normalize_relay_settings_package(
    data: dict[str, Any],
) -> tuple[dict[str, Any], list[tuple[str, str, Any]], dict[str, Any]]:
    """Return (meta, rows[(element, param, value)], flat_dict)."""
    meta = extract_settings_meta(data)
    rows: list[tuple[str, str, Any]] = []

    elements = data.get("elements")
    if not isinstance(elements, dict):
        elements = data.get("protection_elements")
    if isinstance(elements, dict):
        rows.extend(flatten_element_params(elements))

    for key, val in data.items():
        if key in _META_KEYS or str(key).startswith("_"):
            continue
        if isinstance(val, (dict, list)):
            continue
        param = canonical_param(str(key))
        element = "GENERAL"
        m = re.match(r"^(\d{2}[A-Z]{0,3})[_-](.+)$", str(key), re.I)
        if m:
            element = m.group(1).upper()
            param = canonical_param(m.group(2))
        else:
            for prefix in _ELEMENT_PREFIXES:
                if str(key).upper().startswith(prefix):
                    element = prefix
                    break
        rows.append((element, param, val))

    flat: dict[str, Any] = {
        "setting_source": meta["source"],
        "setting_version": meta["version"],
        "setting_group": meta["group"],
        "active_group": meta["group"],
        "version": meta["version"],
        "active_setting_group_verified": meta["verified"],
        "approval_status": meta["approval_status"],
    }
    for el, param, val in rows:
        flat[f"{el}.{param}" if el != "GENERAL" else param] = val
        if el != "GENERAL":
            flat.setdefault(param, val)

    return meta, rows, flat


def map_setting_source(source: str):
    from settings.hierarchy.resolver import SettingSource

    u = (source or "").upper()
    if "EVENT" in u and "SPECIFIC" in u:
        return SettingSource.EVENT_SPECIFIC_ACTIVE
    if "ACTIVE" in u and "GROUP" in u:
        return SettingSource.ACTIVE_SETTING_GROUP
    if "APPROVED" in u or "BASE" in u:
        return SettingSource.APPROVED_RELAY_BASE
    if "HISTORICAL" in u:
        return SettingSource.HISTORICAL
    if "DESIGN" in u:
        return SettingSource.ENGINEERING_DESIGN
    return SettingSource.RELAY_CONFIGURATION


def load_relay_settings_from_files(storage: Any, files: list[Any]) -> tuple[dict[str, Any], list[Any]]:
    """Load settings from event files → (flat_dict, SettingRecord list)."""
    from settings.hierarchy.resolver import SettingRecord

    json_candidates: list[tuple[int, str, dict[str, Any]]] = []
    for ef in files:
        name = (ef.original_filename or "").lower()
        if not name.endswith(".json") or name.endswith("package.json"):
            continue
        try:
            raw = storage.get_bytes(ef.storage_key)
            data = json.loads(raw.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not parse settings JSON %s: %s", name, exc)
            continue
        if not isinstance(data, dict):
            continue
        score = 0
        if looks_like_settings_json(name, data):
            score += 10
        if "setting" in name or "relay" in name:
            score += 5
        if getattr(ef, "source_type", None) == "SETTINGS":
            score += 8
        if score > 0:
            json_candidates.append((score, ef.original_filename or name, data))

    json_candidates.sort(key=lambda t: (-t[0], t[1]))

    for _score, fname, data in json_candidates:
        meta, rows, flat = normalize_relay_settings_package(data)
        if not rows:
            continue
        src = map_setting_source(str(meta["source"]))
        records: list[SettingRecord] = []
        for i, (element, parameter, value) in enumerate(rows):
            enabled_flag: Optional[bool] = None
            if str(parameter).lower() == "enabled" and isinstance(value, bool):
                enabled_flag = value
            records.append(
                SettingRecord(
                    setting_id=f"upload-{element}-{parameter}-{i}",
                    relay_id="NOT VERIFIED",
                    setting_group=str(meta["group"]),
                    parameter=str(parameter),
                    value=value,
                    unit="",
                    enabled=enabled_flag if enabled_flag is not None else True,
                    version=str(meta["version"]),
                    source=src,
                    approval_status=str(meta["approval_status"]),
                    verified=bool(meta["verified"]),
                    element=str(element),
                )
            )
        flat["_source_file"] = fname
        flat["_meta"] = meta
        logger.info(
            "Loaded %d setting parameters from %s (source=%s group=%s verified=%s)",
            len(records),
            fname,
            meta["source"],
            meta["group"],
            meta["verified"],
        )
        return flat, records

    # Text / CSV / XML / SET dumps — prefer vendor ingest (SEL SET_ALL, XRIO, PCM600 CSV)
    from app.services.settings_ingest import (
        ingest_settings_bytes,
        setting_records_from_ingested,
    )

    best: tuple[int, dict[str, Any], list[Any]] | None = None
    for ef in files:
        name = (ef.original_filename or "").lower()
        st = (getattr(ef, "source_type", None) or "").upper()
        is_settings = st == "SETTINGS" or any(
            x in name for x in ("setting", "relay", "param", "set_all", "set_", "xrio")
        )
        if not is_settings and not name.endswith((".set", ".xrio")):
            continue
        if name.endswith((".cfg", ".dat", ".cff")) and "setting" not in name:
            continue
        if not name.endswith((".txt", ".csv", ".set", ".cfg", ".xml", ".xrio", ".json")):
            continue
        # JSON already handled above; skip unless SETTINGS-tagged and empty earlier
        if name.endswith(".json"):
            continue
        try:
            raw = storage.get_bytes(ef.storage_key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read settings file %s: %s", name, exc)
            continue
        ingested = ingest_settings_bytes(raw, filename=ef.original_filename or name)
        if ingested.get("status") != "OK":
            continue
        flat, records = setting_records_from_ingested(ingested)
        score = len(records) + int(ingested.get("param_count") or 0)
        if st == "SETTINGS":
            score += 20
        if best is None or score > best[0]:
            best = (score, flat, records)

    if best and best[2]:
        logger.info(
            "Loaded %d setting parameters via vendor ingest from %s",
            len(best[2]),
            best[1].get("_source_file"),
        )
        return best[1], best[2]

    # Legacy KEY=VALUE text fallback
    out: dict[str, Any] = {}
    source_name = ""
    for ef in files:
        name = (ef.original_filename or "").lower()
        st = (getattr(ef, "source_type", None) or "").upper()
        if st != "SETTINGS" and not any(x in name for x in ("setting", "relay", "param")):
            continue
        if name.endswith((".cfg", ".dat", ".cff")) and "setting" not in name:
            continue
        if not name.endswith((".txt", ".csv", ".set", ".cfg")):
            continue
        try:
            text = storage.get_bytes(ef.storage_key).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read settings text %s: %s", name, exc)
            continue
        source_name = ef.original_filename or name
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith(";"):
                continue
            if "|" in line:
                cols = [c.strip() for c in line.split("|")]
                if len(cols) >= 2 and cols[0].lower() not in ("parameter", "param"):
                    key, val = cols[0], cols[1]
                    if key and val and val != "-":
                        out[canonical_param(key)] = val
                continue
            sep = None
            for candidate in ("=", ":", "\t"):
                if candidate in line:
                    sep = candidate
                    break
            if not sep:
                continue
            key, _, val = line.partition(sep)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if not key or not val:
                continue
            ckey = canonical_param(key)
            try:
                out[ckey] = float(val) if "." in val else int(val)
            except ValueError:
                low = val.lower()
                if low in ("true", "yes", "on", "enabled"):
                    out[ckey] = True
                elif low in ("false", "no", "off", "disabled"):
                    out[ckey] = False
                else:
                    out[ckey] = val
        if out:
            break

    if not out:
        return {}, []

    meta = apply_upload_auto_approval(
        {
            "source": "RELAY_CONFIGURATION",
            "version": "UPLOADED",
            "group": "Base",
            "verified": False,
            "approval_status": "NOT VERIFIED",
        }
    )
    out["_source_file"] = source_name
    out["_meta"] = meta
    records = []
    for i, (key, val) in enumerate(list(out.items())):
        if str(key).startswith("_"):
            continue
        element = "GENERAL"
        for prefix in _ELEMENT_PREFIXES:
            if str(key).upper().startswith(prefix):
                element = prefix
                break
        records.append(
            SettingRecord(
                setting_id=f"upload-txt-{key}-{i}",
                relay_id="UPLOADED",
                setting_group="Base",
                parameter=str(key),
                value=val,
                unit="",
                enabled=True,
                version="UPLOADED",
                source=map_setting_source(str(meta["source"])),
                approval_status=str(meta["approval_status"]),
                verified=bool(meta["verified"]),
                element=element,
            )
        )
    return out, records
