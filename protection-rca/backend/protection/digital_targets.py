"""DR digital targets — map COMTRADE status channels to operate evidence roles.

Industry practice (SIGRA / DME review): treat digitals as relay *targets*
(pickup, trip, 52a, …), optionally remapped when vendor names are opaque.
"""

from __future__ import annotations

import re
from typing import Any, Optional

# Target role → timeline event_type
TARGET_TO_EVENT: dict[str, str] = {
    "PICKUP": "protection_pickup",
    "START": "protection_pickup",
    "TRIP": "protection_trip",
    "OPERATE": "protection_trip",
    "52A": "52a_change",
    "52B": "52b_change",
    "RECLOSE": "reclose",
    "LOCKOUT": "lockout",
    "INTERTRIP": "intertrip",
    "COMM": "communication_signal",
    "BF": "breaker_trip_command",
    "BLOCK": "protection_pickup",  # e.g. 68 block asserted
    "IGNORE": "",
    "UNKNOWN": "",
}

VALID_TARGET_ROLES = frozenset(TARGET_TO_EVENT.keys())

_INFER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"PICK\s*UP|PU_|_PU\b|START|ZONE\s*\d*|Z[123]\b", re.I), "PICKUP"),
    (re.compile(r"TRIP|TR\b|_TR\b|OPERATE|_OP\b|(?<![A-Z0-9])OP\b", re.I), "TRIP"),
    (re.compile(r"52A|52_A|BREAKER.*A\b|CB.*52A", re.I), "52A"),
    (re.compile(r"52B|52_B|BREAKER.*B\b|CB.*52B", re.I), "52B"),
    (re.compile(r"RECLOSE|79\b|AR\b|AUTO.?RECLOSE", re.I), "RECLOSE"),
    (re.compile(r"LOCKOUT|86\b|\bLO\b", re.I), "LOCKOUT"),
    (re.compile(r"INTERTRIP|TRANSFER.?TRIP|\bTT\b", re.I), "INTERTRIP"),
    (re.compile(r"COMM|PILOT|CARRIER|POTT|DUTT", re.I), "COMM"),
    (re.compile(r"BF|50BF|BREAKER.?FAIL", re.I), "BF"),
    (re.compile(r"BLOCK|68\b|PSB", re.I), "BLOCK"),
]


def infer_target_role(channel_name: str) -> str:
    for pat, role in _INFER_PATTERNS:
        if pat.search(channel_name or ""):
            return role
    return "UNKNOWN"


def infer_element_code(channel_name: str) -> Optional[str]:
    """Reuse ANSI matcher from protection engine (lazy import)."""
    from protection.engine import _match_element_from_channel

    return _match_element_from_channel(channel_name or "")


def normalize_digital_map(raw: Optional[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """
    Accept either:
      { "CH": {"role": "TRIP", "element": "21"} }
    or flat:
      { "CH": "TRIP|21" } / { "CH": "TRIP" }
    """
    out: dict[str, dict[str, str]] = {}
    if not isinstance(raw, dict):
        return out
    for name, val in raw.items():
        key = str(name).strip()
        if not key:
            continue
        role = "UNKNOWN"
        element = ""
        if isinstance(val, dict):
            role = str(val.get("role") or val.get("target") or "UNKNOWN").upper().strip()
            element = str(val.get("element") or "").upper().strip()
        else:
            s = str(val).upper().strip()
            if "|" in s:
                role, element = (p.strip() for p in s.split("|", 1))
            else:
                role = s
        if role not in VALID_TARGET_ROLES:
            role = "UNKNOWN"
        if element in ("", "NONE", "NULL", "-"):
            element = ""
        out[key] = {"role": role, "element": element}
    return out


def resolve_digital_target(
    channel_name: str,
    *,
    digital_map: Optional[dict[str, Any]] = None,
) -> tuple[str, Optional[str]]:
    """Return (target_role, element_code) using map override then inference."""
    cleaned = normalize_digital_map(digital_map)
    if channel_name in cleaned:
        entry = cleaned[channel_name]
        role = entry.get("role") or "UNKNOWN"
        el = entry.get("element") or None
        if not el:
            el = infer_element_code(channel_name)
        return role, el or None
    role = infer_target_role(channel_name)
    return role, infer_element_code(channel_name)


def target_to_event_type(role: str) -> Optional[str]:
    et = TARGET_TO_EVENT.get(str(role).upper().strip(), "")
    return et or None


def is_assert_transition(
    frm: int,
    to: int,
    *,
    normal_state: int = 0,
) -> bool:
    """True when the transition is an operate/assert edge (DR target fires).

    Rising edge when normal_state=0 (usual); falling edge when normal_state=1.
    """
    try:
        ns = int(normal_state)
    except (TypeError, ValueError):
        ns = 0
    if ns == 1:
        return int(frm) == 1 and int(to) == 0
    return int(frm) == 0 and int(to) == 1
