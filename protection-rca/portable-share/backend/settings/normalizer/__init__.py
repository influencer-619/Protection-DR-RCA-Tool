"""Setting normalizer stubs — pass-through with explicit units."""

from __future__ import annotations

from typing import Any


def normalize_value(value: Any, unit: str, target_unit: str | None = None) -> Any:
    """Normalize setting values. Returns value unchanged if conversion not defined."""
    if target_unit is None or unit == target_unit or value is None:
        return value
    # Explicit: no silent unit invention
    return value


def normalize_enabled(raw: Any) -> bool | None:
    if raw is None:
        return None
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return bool(raw)
    s = str(raw).strip().upper()
    if s in ("TRUE", "YES", "1", "ON", "ENABLED"):
        return True
    if s in ("FALSE", "NO", "0", "OFF", "DISABLED"):
        return False
    return None
