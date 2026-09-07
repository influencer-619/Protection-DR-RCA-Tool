"""Deterministic IEC/ANSI time-overcurrent and distance zone physics."""

from __future__ import annotations

import math
from typing import Any, Optional


# IEC 60255-151 / IEEE C37.112 style inverse curves (A, B, p)
IEC_CURVES: dict[str, dict[str, float]] = {
    "IEC_NORMAL_INVERSE": {"A": 0.14, "B": 0.02, "p": 0.02},
    "IEC_VERY_INVERSE": {"A": 13.5, "B": 0.0, "p": 1.0},
    "IEC_EXTREMELY_INVERSE": {"A": 80.0, "B": 0.0, "p": 2.0},
    "IEC_LONG_TIME_INVERSE": {"A": 120.0, "B": 0.0, "p": 1.0},
    "IEEE_MODERATELY_INVERSE": {"A": 0.0515, "B": 0.114, "p": 0.02},
    "IEEE_VERY_INVERSE": {"A": 19.61, "B": 0.491, "p": 2.0},
    "IEEE_EXTREMELY_INVERSE": {"A": 28.2, "B": 0.1217, "p": 2.0},
}


def resolve_curve_name(name: Optional[str]) -> str:
    if not name:
        return "IEC_NORMAL_INVERSE"
    key = str(name).strip().upper().replace("-", "_").replace(" ", "_")
    aliases = {
        "NI": "IEC_NORMAL_INVERSE",
        "VI": "IEC_VERY_INVERSE",
        "EI": "IEC_EXTREMELY_INVERSE",
        "LTI": "IEC_LONG_TIME_INVERSE",
        "NORMAL_INVERSE": "IEC_NORMAL_INVERSE",
        "VERY_INVERSE": "IEC_VERY_INVERSE",
        "EXTREMELY_INVERSE": "IEC_EXTREMELY_INVERSE",
    }
    key = aliases.get(key, key)
    if key not in IEC_CURVES:
        return "IEC_NORMAL_INVERSE"
    return key


def inverse_time_s(
    *,
    multiple: float,
    time_dial: float,
    curve: str = "IEC_NORMAL_INVERSE",
) -> Optional[float]:
    """
    Operate time t = TDS * (A / (M^p - 1) + B) for M > 1.

    Returns None when M <= 1 (no operate) or invalid inputs.
    Never invents a time when pickup multiple cannot be formed.
    """
    if multiple is None or time_dial is None:
        return None
    try:
        m = float(multiple)
        tds = float(time_dial)
    except (TypeError, ValueError):
        return None
    if m <= 1.0 or tds < 0:
        return None
    cname = resolve_curve_name(curve)
    params = IEC_CURVES[cname]
    denom = m ** params["p"] - 1.0
    if abs(denom) < 1e-12:
        return None
    t = tds * (params["A"] / denom + params["B"])
    if not math.isfinite(t) or t < 0:
        return None
    return float(t)


def pickup_multiple(
    current_a: Optional[float],
    pickup_a: Optional[float],
) -> Optional[float]:
    if current_a is None or pickup_a is None:
        return None
    try:
        i = float(current_a)
        ip = float(pickup_a)
    except (TypeError, ValueError):
        return None
    if ip <= 0:
        return None
    return i / ip


def zone_entry(
    *,
    apparent_z_ohm: Optional[complex],
    zone_reach_ohm: Optional[float],
    zone_angle_deg: float = 75.0,
    shape: str = "mho",
) -> dict[str, Any]:
    """
    Simple mho/quadrilateral reach check.

    If inputs missing → status NOT_CALCULABLE (never invents zone entry).
    """
    if apparent_z_ohm is None or zone_reach_ohm is None:
        return {
            "status": "NOT_CALCULABLE",
            "in_zone": None,
            "reason": "Apparent impedance or zone reach NOT AVAILABLE",
        }
    try:
        z = complex(apparent_z_ohm)
        reach = float(zone_reach_ohm)
    except (TypeError, ValueError):
        return {
            "status": "NOT_CALCULABLE",
            "in_zone": None,
            "reason": "Invalid impedance / reach values",
        }
    if reach <= 0:
        return {
            "status": "NOT_CALCULABLE",
            "in_zone": None,
            "reason": "Zone reach must be > 0",
        }

    shape_l = (shape or "mho").lower()
    if shape_l == "mho":
        # Classic mho: |Z - Z_reach/2| <= |Z_reach/2| along characteristic angle
        ang = math.radians(zone_angle_deg)
        z_set = reach * complex(math.cos(ang), math.sin(ang))
        center = z_set / 2.0
        radius = abs(z_set) / 2.0
        in_zone = abs(z - center) <= radius * 1.001
    else:
        # Simple rectangular forward reach (quad approximation)
        r, x = z.real, z.imag
        in_zone = (0 <= r <= reach * 0.3) and (0 <= x <= reach)

    return {
        "status": "CALCULATED",
        "in_zone": bool(in_zone),
        "shape": shape_l,
        "reach_ohm": reach,
        "z_mag_ohm": abs(z),
        "z_angle_deg": math.degrees(math.atan2(z.imag, z.real)),
        "method": "mho_circle" if shape_l == "mho" else "quad_approx",
        "algorithm_version": "1.0.0",
    }
