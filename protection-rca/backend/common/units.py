"""Canonical electrical unit normalization (A, V, kV, Ω, Hz, km)."""

from __future__ import annotations

from typing import Optional


def normalize_unit(raw: Optional[str], *, role: str = "") -> str:
    """Map vendor COMTRADE uu / role hints to a display unit."""
    u = (raw or "").strip()
    ul = u.lower().replace(" ", "")
    role_u = (role or "").upper()

    # Explicit vendor forms
    if ul in ("a", "amp", "amps", "ampere", "amperes"):
        return "A"
    if ul in ("ka", "kiloamp", "kiloamps"):
        return "kA"
    if ul in ("v", "volt", "volts"):
        return "V"
    if ul in ("kv", "kilovolt", "kilovolts"):
        return "kV"
    if ul in ("ohm", "ohms", "ω", "Ω"):
        return "Ω"
    if ul in ("hz", "hertz"):
        return "Hz"
    if ul in ("km", "kilometer", "kilometre"):
        return "km"
    if ul in ("ms", "millisecond", "milliseconds"):
        return "ms"
    if ul in ("s", "sec", "second", "seconds"):
        return "s"
    if ul in ("deg", "degree", "degrees", "°"):
        return "°"
    if ul in ("w", "watt", "watts"):
        return "W"
    if ul in ("va", "var"):
        return u.upper() if u else "VA"
    if ul in ("pu", "p.u."):
        return "pu"

    # Role-based fallback when COMTRADE unit blank
    if role_u.startswith("I"):
        return "A"
    if role_u.startswith("V"):
        return "V"
    if "Z" in role_u or "IMP" in role_u:
        return "Ω"
    if "F" == role_u or "FREQ" in role_u:
        return "Hz"

    return u or ""


def to_si_voltage_scale(unit: Optional[str]) -> float:
    """Multiply voltage magnitude by this to convert to volts."""
    n = normalize_unit(unit)
    if n == "kV":
        return 1000.0
    return 1.0


def to_si_current_scale(unit: Optional[str]) -> float:
    """Multiply current magnitude by this to convert to amperes."""
    n = normalize_unit(unit)
    if n == "kA":
        return 1000.0
    return 1.0


def infer_unit_from_quantity(quantity: str, fallback: str = "") -> str:
    q = (quantity or "").upper()
    if "_RMS" in q or q.startswith("I") or "CURRENT" in q:
        if "KA" in q:
            return "kA"
        return normalize_unit(fallback, role="I") or "A"
    if q.startswith("V") or "VOLT" in q:
        if "KV" in q:
            return "kV"
        return normalize_unit(fallback, role="V") or "V"
    if q.startswith("Z") or q.startswith("R_") or "IMPED" in q:
        return "Ω"
    if "FREQ" in q or q == "F":
        return "Hz"
    if "KM" in q or "DISTANCE" in q:
        return "km"
    return normalize_unit(fallback) or fallback or ""
