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
    "ALARM": "",  # advisory (e.g. thermal alarm) — not a trip sequence step
    "IGNORE": "",
    "UNKNOWN": "",
}

VALID_TARGET_ROLES = frozenset(TARGET_TO_EVENT.keys())

_INFER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Spare / unused CFG slots
    (re.compile(r"^UNUSED(?:#\d+)?$", re.I), "IGNORE"),
    # Unlabeled programmable relay outputs (MiCOM "Relay 1" …) — not operate evidence
    (re.compile(r"^RELAY\s*\d+$", re.I), "IGNORE"),
    # Watchdog / unlabeled binary inputs — not protection evidence
    (re.compile(r"WATCHDOG|DIGITAL\s*INPUT\s*\d+", re.I), "IGNORE"),
    # Station interlocking / supervision — not pickup/trip evidence
    (re.compile(
        r"SYNCH?\s*PERMIT|VTS|PT\s*NOT\s*SER|BUS_VOLTAGE|MLC_|TSS_ON|RB_ACTIVE|"
        r"STN_SUPPLY|AM_SWITCH|^TCS$|CHECK.?SYNC|SYNC.?CHECK",
        re.I,
    ), "IGNORE"),
    # Recorder / capture status — not protection operate evidence
    (re.compile(
        r"TRIG\.?\s*WAVE|WAVE\.?\s*CAP|FLTREC|FLAG\s*LOST|RECORDER|DR\s*TRIG|FAULT\s*REC",
        re.I,
    ), "IGNORE"),
    # Motor thermal alarm (before generic TRIP / START)
    (re.compile(
        r"THERMAL\s*ALARM|TH(?:ERMAL)?\s*ALARM|TEMP(?:ERATURE)?\s*ALARM|\b49\s*ALARM\b",
        re.I,
    ), "ALARM"),
    # Motor stall / locked rotor (operate → trip)
    (re.compile(
        r"STALL|LOCKED?\s*ROTOR|ROTOR.?STALL|\b48\b",
        re.I,
    ), "TRIP"),
    # BF / LBB before generic OPTD so "LBB OPTD" is not classed as trip
    (re.compile(r"BF|50BF|BFAIL|BRK.?FAIL|BREAKER.?FAIL|\bLBB\b", re.I), "BF"),
    # Harmonic / inrush blocking (Siemens 87 BLK 2nd H / nth H / CWA)
    (re.compile(
        r"BLOCK|\bBLK\b|68\b|PSB|INRUSH|2ND\s*H|NTH\s*H|\bCWA\b|HARM(?:ONIC)?\s*BLK",
        re.I,
    ), "BLOCK"),
    # Intertrip / transfer trip BEFORE bare TRIP (substring "TRIP" inside INTERTRIP)
    (re.compile(r"INTERTRIP|TRANSFER.?TRIP|(?<![A-Z0-9])TT\b", re.I), "INTERTRIP"),
    # Trip / operate BEFORE zone/start heuristics so "21_Z1_TRIP" is not PICKUP
    # (incl. station DFR "… OPTD"; CFG may truncate "Trip"→"Ti")
    (re.compile(
        r"TRIP|UNIT\s*TI\b|(?<![A-Z0-9])TR\b|_TR\b|OPERAT(?:E|ED)?|\bOPTD\b|_OP\b|(?<![A-Z0-9])OP\b",
        re.I,
    ), "TRIP"),
    # Vendor-neutral pickup: PICKUP / PU / START / zone+PU / DST ST
    # Bare Z1/ZONE alone is not enough (would steal "21_Z1_TRIP").
    (re.compile(
        r"PICK(?:ED)?\s*UP|(?<![A-Za-z])PU(?![A-Za-z0-9])|"
        r"(?<![A-Za-z])START(?:ED)?(?![A-Za-z])|"
        r"ZONE\s*\d*\s*(?:PICK|START|PU)|Z[123](?:_|\s)*(?:PICK|START|PU)|"
        r"PROLONGED\s*START|LONG\s*START|ANY\s*START|"
        r"DST\s*ST|DSTST",
        re.I,
    ), "PICKUP"),
    # Breaker status — 52a / CB open (BKR OFF, BREAKER OFF, …)
    (re.compile(
        r"52A|52_A|CB.*52A|BKR\s*OFF|BREAKER\s*OFF|CB\s*OFF|CB\s*AUX",
        re.I,
    ), "52A"),
    (re.compile(r"52B|52_B|BREAKER.*B\b|CB.*52B", re.I), "52B"),
    # AR inhibit — supervisory only (do not treat as reclose operate / 79 pickup)
    (re.compile(
        r"INHIBIT\s*AR|AR_?INHIBIT|AR\s*INHIBIT|79\s*INHIBIT|INHIBIT.?RECLOSE",
        re.I,
    ), "BLOCK"),
    # Autoreclose initiate / close / success (not bare A/R or lone 79)
    (re.compile(
        r"AUTO.?RECLOSE|RECLOSE|INITIATE_?AR|"
        r"\bRREC\d*\b|\b79\s*(?:AR|RECLOSE|RREC)\b|"
        r"\bAR\s*(?:INIT|CLOSE|ON|OFF|SUCCESS)",
        re.I,
    ), "RECLOSE"),
    (re.compile(r"LOCKOUT|\b86\b|LOCK.?OUT", re.I), "LOCKOUT"),
    # Word-ish COMM — avoid matching inside RECOMMENDATION
    (re.compile(
        r"(?<![A-Z])COMM(?![A-Z])|PILOT|CARRIER|(?<![A-Z])CARR\b|POTT|DUTT",
        re.I,
    ), "COMM"),
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
