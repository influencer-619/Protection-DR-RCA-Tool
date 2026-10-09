"""ANSI / IEEE C37.2 device numbers → short technical names for UI and RCA text."""

from __future__ import annotations

import re
from typing import Optional

# Canonical technical names (IEEE C37.2 device function numbers / common utility usage).
ANSI_TECHNICAL_NAMES: dict[str, str] = {
    "21": "Distance protection",
    "21P": "Phase distance",
    "21G": "Ground distance",
    "21N": "Ground distance",
    "25": "Synchronism check",
    "27": "Undervoltage",
    "32": "Directional power",
    "32R": "Reverse power",
    "46": "Negative-sequence overcurrent",
    "47": "Phase-sequence voltage",
    "48": "Incomplete sequence / stalled rotor",
    "49": "Thermal overload",
    "50": "Instantaneous overcurrent",
    "50P": "Phase instantaneous overcurrent",
    "50N": "Neutral / earth instantaneous overcurrent",
    "50G": "Ground instantaneous overcurrent",
    "50BF": "Breaker failure",
    "50NBF": "Neutral breaker failure",
    "51": "Time overcurrent",
    "51P": "Phase time overcurrent",
    "51N": "Neutral / earth time overcurrent",
    "51G": "Ground time overcurrent",
    "59": "Overvoltage",
    "67": "Directional overcurrent",
    "67P": "Phase directional overcurrent",
    "67N": "Neutral / earth directional overcurrent",
    "67G": "Ground directional overcurrent",
    "68": "Power-swing block",
    "78": "Out-of-step / loss of synchronism",
    "79": "Autoreclose",
    "81": "Frequency",
    "81U": "Underfrequency",
    "81O": "Overfrequency",
    "81R": "Rate of change of frequency (ROCOF)",
    "86": "Lockout / master trip",
    "87": "Differential",
    "87B": "Bus differential",
    "87L": "Line differential",
    "87T": "Transformer differential",
    "87G": "Generator differential",
    "87GT": "Generator-transformer differential",
    "87RGF": "Restricted earth-fault (REF)",
    "62BF": "Breaker-failure timer",
    "LBB": "Local breaker backup",
}


def normalize_ansi_code(code: str | None) -> str:
    raw = str(code or "").strip().upper()
    if not raw or raw in ("UNKNOWN", "GENERAL", "—", "-"):
        return ""
    # Strip trailing stage digits sometimes glued (50P1 → 50P) for name lookup only
    return raw


def ansi_technical_name(code: str | None) -> Optional[str]:
    """Return technical name for an ANSI/IEEE device code, or None if unknown."""
    c = normalize_ansi_code(code)
    if not c:
        return None
    if c in ANSI_TECHNICAL_NAMES:
        return ANSI_TECHNICAL_NAMES[c]
    # Soft fallback: drop trailing stage digit (51P1 → 51P)
    m = re.match(r"^([0-9]+[A-Z]*?)(\d+)$", c)
    if m and m.group(1) in ANSI_TECHNICAL_NAMES:
        return ANSI_TECHNICAL_NAMES[m.group(1)]
    return None


def format_ansi(code: str | None, *, with_parens: bool = True) -> str:
    """``50BF (Breaker failure)`` — code alone if name unknown."""
    c = normalize_ansi_code(code) or str(code or "").strip()
    if not c:
        return "—"
    name = ansi_technical_name(c)
    if not name:
        return c
    return f"{c} ({name})" if with_parens else f"{c} {name}"


def format_ansi_list(codes: list[str] | tuple[str, ...] | None) -> str:
    if not codes:
        return ""
    return ", ".join(format_ansi(c) for c in codes if str(c or "").strip())
