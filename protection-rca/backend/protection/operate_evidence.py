"""Operate-evidence gate — industry practice (COMTRADE + relay SER/report).

Policy (NERC PRC-002 / SEL / DFRDA+DPRDA style):
  1. COMTRADE ``digital:`` status channels — primary, sample-aligned asserts.
  2. Relay SER / event report — valid when a clear element is mapped
     (e.g. 21_Z1_PICKUP, RREC1). Never invent from bare ``79`` / ``AR``.
  3. Station / SCADA SOE (breaker aux, vague alarms) — timeline context only.
  4. Settings YAML / electrical inference alone — never assert pickup/trip.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Timeline event types that may assert protection operate
_OPERATE_EVENT_TYPES = frozenset(
    {
        "protection_pickup",
        "protection_trip",
        "breaker_trip_command",
        "reclose",
        "lockout",
    }
)

_SCHEME_STATUS = frozenset({"79", "86", "25"})


def is_digital_timeline_source(source: str | None) -> bool:
    return str(source or "").startswith("digital:")


def digital_channel_from_source(source: str | None) -> str:
    src = str(source or "")
    if src.startswith("digital:"):
        return src.split(":", 1)[1].strip()
    return ""


def is_relay_event_report_source(source: str | None) -> bool:
    return str(source or "").upper().startswith("RELAY_EVENT_REPORT:")


def is_soe_timeline_source(source: str | None) -> bool:
    return str(source or "").upper().startswith("SOE:")


def evidence_quality_of(ev: Any) -> str:
    """Return digital | relay_ser | station_soe | none."""
    src = getattr(ev, "source", None)
    if src is None and isinstance(ev, dict):
        src = ev.get("source")
    src_s = str(src or "")
    if is_digital_timeline_source(src_s):
        return "digital"
    meta = getattr(ev, "metadata", None)
    if meta is None and isinstance(ev, dict):
        meta = ev.get("metadata")
    meta = meta if isinstance(meta, dict) else {}
    q = str(meta.get("evidence_quality") or "").strip().lower()
    if q in ("digital", "relay_ser", "station_soe"):
        return q
    if is_relay_event_report_source(src_s):
        return "relay_ser"
    if is_soe_timeline_source(src_s):
        return "station_soe"
    return "none"


def _event_type(ev: Any) -> str:
    et = getattr(ev, "event_type", None)
    if et is None and isinstance(ev, dict):
        et = ev.get("event_type")
    return str(et or "").strip().lower()


def _meta(ev: Any) -> dict[str, Any]:
    meta = getattr(ev, "metadata", None)
    if meta is None and isinstance(ev, dict):
        meta = ev.get("metadata")
    return meta if isinstance(meta, dict) else {}


def _element_code(ev: Any) -> Optional[str]:
    meta = _meta(ev)
    code = str(meta.get("element") or "").upper().strip()
    return code or None


def _signal_label(ev: Any) -> str:
    meta = _meta(ev)
    for key in ("point_tag", "signal", "label", "channel"):
        v = meta.get(key)
        if v:
            return str(v).strip()
    src = str(getattr(ev, "source", "") or "")
    if ":" in src:
        return src.split(":", 1)[1].strip()
    return ""


def ser_evidence_token(ev: Any) -> str:
    """Stable evidence id for a relay SER / event-report assert."""
    label = _signal_label(ev) or "unnamed"
    src = str(getattr(ev, "source", "") or "")
    if is_relay_event_report_source(src):
        return f"report:{label}"
    return f"ser:{label}"


def is_assertable_timeline_event(ev: Any) -> bool:
    """True when this timeline row may set element pickup/trip.

    COMTRADE digitals always (channel resolved later).
    Relay SER / event report only with clear element + operate event type.
    Station SOE never asserts protection elements.
    """
    q = evidence_quality_of(ev)
    if q == "digital":
        return True
    if q != "relay_ser":
        return False
    if _event_type(ev) not in _OPERATE_EVENT_TYPES:
        return False
    code = _element_code(ev)
    if not code:
        return False
    # Scheme-status still needs clear wording in the signal (already enforced
    # when element was assigned); bare codes alone never reach here as 79.
    if code in _SCHEME_STATUS:
        label = _signal_label(ev)
        if code == "79" and not re.search(
            r"AUTO.?RECLOSE|RECLOSE|\bRREC|INITIATE_?AR|"
            r"\b79\s*(?:AR|RECLOSE|RREC)\b|"
            r"\bAR\s*(?:INIT|CLOSE|ON|OFF|SUCCESS)",
            label,
            re.I,
        ):
            return False
        if code == "86" and not re.search(r"LOCKOUT|LOCK.?OUT|\b86\s*(?:LOCK|TRIP)", label, re.I):
            return False
        if code == "25" and not re.search(r"SYNC|RSYN|\b25\s*SYNC", label, re.I):
            return False
    return True


def operate_evidence_token(ev: Any) -> str:
    """Token stored on ElementObservation.channel_evidence / evidence_ids."""
    q = evidence_quality_of(ev)
    if q == "digital":
        ch = digital_channel_from_source(getattr(ev, "source", None))
        return ch or _signal_label(ev)
    return ser_evidence_token(ev)


def observation_has_operate_evidence(obs: Any) -> bool:
    evid = getattr(obs, "channel_evidence", None) or []
    return any(_token_is_valid_operate_evidence(str(e)) for e in evid)


def _token_is_valid_operate_evidence(s: str) -> bool:
    t = (s or "").strip()
    if not t:
        return False
    low = t.lower()
    if t.upper().startswith("PHYS-"):
        return False
    # Legacy bare soe: without ser:/report: — not assert-grade
    if low.startswith("soe:") and not low.startswith("soe:ser"):
        return False
    # Accept COMTRADE channel names, ser:, report:, digital:
    return True


def assessment_has_operate_evidence(a: dict[str, Any] | None) -> bool:
    """True when assessment has COMTRADE or relay-SER operate evidence."""
    if not isinstance(a, dict):
        return False
    evid = a.get("evidence_ids") or a.get("channel_evidence") or []
    if not evid:
        meta = a.get("metadata") if isinstance(a.get("metadata"), dict) else {}
        evid = meta.get("channel_evidence") or meta.get("operate_channels") or []
    if not isinstance(evid, (list, tuple)):
        return False
    return any(_token_is_valid_operate_evidence(str(e)) for e in evid)


def clamp_assessment_operate_flags(a: dict[str, Any]) -> dict[str, Any]:
    """Force pickup/trip off when assessment has no operate evidence."""
    if not isinstance(a, dict):
        return a
    if assessment_has_operate_evidence(a):
        return a
    out = dict(a)
    if a.get("pickup"):
        out["pickup"] = False
    if a.get("trip"):
        out["trip"] = False
    return out
