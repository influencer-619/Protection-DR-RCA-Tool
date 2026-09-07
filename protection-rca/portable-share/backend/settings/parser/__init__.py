"""Setting parsers — structured dict ingest only (no invented fields)."""

from __future__ import annotations

from typing import Any

from settings.hierarchy.resolver import SettingRecord, SettingSource
from settings.normalizer import normalize_enabled


def parse_setting_dict(data: dict[str, Any]) -> SettingRecord | None:
    """Parse a setting dict. Returns None if required fields missing."""
    required = ("setting_id", "relay_id", "parameter", "source")
    if any(k not in data for k in required):
        return None
    try:
        source = SettingSource(str(data["source"]))
    except ValueError:
        return None
    return SettingRecord(
        setting_id=str(data["setting_id"]),
        relay_id=str(data["relay_id"]),
        setting_group=str(data.get("setting_group", "")),
        parameter=str(data["parameter"]),
        value=data.get("value"),
        unit=str(data.get("unit", "")),
        enabled=normalize_enabled(data.get("enabled")),
        effective_from=data.get("effective_from"),
        effective_to=data.get("effective_to"),
        version=str(data.get("version", "")),
        source=source,
        approval_status=str(data.get("approval_status", "DRAFT")),
        verified=bool(data.get("verified", False)),
        element=str(data.get("element", "")),
    )


def parse_settings_list(items: list[dict[str, Any]]) -> list[SettingRecord]:
    out: list[SettingRecord] = []
    for item in items:
        rec = parse_setting_dict(item)
        if rec is not None:
            out.append(rec)
    return out
