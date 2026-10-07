"""Serialize datetimes for the API."""

from __future__ import annotations

from datetime import datetime, timezone


def to_utc_iso(dt: datetime | None) -> str | None:
    """App timestamps (created_at, …). Naive values are treated as UTC."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def to_dr_wall_iso(dt: datetime | None) -> str | None:
    """COMTRADE / relay disturbance time — wall clock as on the DR, no TZ shift.

    CFG stamps are plant/relay local (or unspecified). Attaching Z would make
    browsers convert (e.g. 20:12 → 01:42 next day in IST).
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt.isoformat(sep="T")
