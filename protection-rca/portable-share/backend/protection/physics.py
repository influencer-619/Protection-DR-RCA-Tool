"""Physics helpers for differential, directional, and breaker-failure elements."""

from __future__ import annotations

import cmath
import math
from typing import Any, Optional


def _c(val: Any) -> Optional[complex]:
    if val is None:
        return None
    if isinstance(val, complex):
        return val
    if isinstance(val, dict):
        if "real" in val and "imag" in val:
            try:
                return complex(float(val["real"]), float(val["imag"]))
            except (TypeError, ValueError):
                return None
        if "magnitude" in val and "angle_deg" in val:
            try:
                return cmath.rect(
                    float(val["magnitude"]), math.radians(float(val["angle_deg"]))
                )
            except (TypeError, ValueError):
                return None
    return None


def differential_operate_restraint(
    *,
    i_local: Optional[complex] = None,
    i_remote: Optional[complex] = None,
    i_w1: Optional[complex] = None,
    i_w2: Optional[complex] = None,
    slope: float = 0.3,
    pickup_a: float = 0.2,
) -> dict[str, Any]:
    """
    Classic percentage differential: Id = |I1 - I2|, Ir = (|I1| + |I2|) / 2.

    For line 87L use local/remote; for transformer 87T use winding currents.
    Missing phasors → NOT_CALCULABLE (never invents operate).
    """
    a = i_local if i_local is not None else i_w1
    b = i_remote if i_remote is not None else i_w2
    if a is None or b is None:
        return {
            "status": "NOT_CALCULABLE",
            "operate_a": None,
            "restraint_a": None,
            "pickup_a": pickup_a,
            "slope": slope,
            "operate_expected": None,
            "notes": "Both-side current phasors required for operate/restraint",
        }
    operate = abs(a - b)
    restraint = 0.5 * (abs(a) + abs(b))
    threshold = pickup_a + slope * restraint
    expect = operate > threshold
    return {
        "status": "OK",
        "operate_a": float(operate),
        "restraint_a": float(restraint),
        "threshold_a": float(threshold),
        "pickup_a": pickup_a,
        "slope": slope,
        "operate_expected": bool(expect),
        "notes": "Id = |I1−I2|, Ir = (|I1|+|I2|)/2, trip if Id > Ip + k·Ir",
    }


def directional_67(
    *,
    i_fault: Optional[complex],
    v_polarize: Optional[complex],
    forward_region_deg: float = 90.0,
    max_torque_angle_deg: float = -45.0,
) -> dict[str, Any]:
    """
    Torque-like directional decision: angle(I) − angle(V) relative to MTA.

    Positive torque in forward sector → FORWARD; reverse → REVERSE.
    """
    if i_fault is None or v_polarize is None:
        return {
            "status": "NOT_CALCULABLE",
            "direction": None,
            "angle_deg": None,
            "notes": "Fault current and polarizing voltage phasors required",
        }
    if abs(i_fault) < 1e-9 or abs(v_polarize) < 1e-9:
        return {
            "status": "NOT_CALCULABLE",
            "direction": None,
            "angle_deg": None,
            "notes": "Near-zero I or V — direction not calculable",
        }
    ang = math.degrees(cmath.phase(i_fault) - cmath.phase(v_polarize))
    # Normalize to [-180, 180]
    while ang > 180:
        ang -= 360
    while ang < -180:
        ang += 360
    # Torque angle relative to MTA
    torque_ang = ang - max_torque_angle_deg
    while torque_ang > 180:
        torque_ang -= 360
    while torque_ang < -180:
        torque_ang += 360
    half = abs(forward_region_deg) / 2.0
    if abs(torque_ang) <= half:
        direction = "FORWARD"
    elif abs(abs(torque_ang) - 180) <= half:
        direction = "REVERSE"
    else:
        direction = "INCONCLUSIVE"
    return {
        "status": "OK",
        "direction": direction,
        "angle_deg": float(ang),
        "torque_angle_deg": float(torque_ang),
        "mta_deg": max_torque_angle_deg,
        "forward_region_deg": forward_region_deg,
        "notes": "Direction from arg(I)−arg(Vpol) vs max-torque angle",
    }


def breaker_failure_timing(
    *,
    trip_time_s: Optional[float],
    current_drop_time_s: Optional[float],
    bf_timer_s: Optional[float] = None,
    current_persists: bool = False,
) -> dict[str, Any]:
    """
    50BF timing: after trip command, current should interrupt within BF timer.

    Does not auto-declare BF malfunction — INCONCLUSIVE without timer setting.
    """
    if trip_time_s is None:
        return {
            "status": "NOT_CALCULABLE",
            "bf_expected": None,
            "clearing_time_s": None,
            "notes": "Trip command timestamp NOT AVAILABLE",
        }
    clearing = None
    if current_drop_time_s is not None:
        clearing = float(current_drop_time_s) - float(trip_time_s)

    if bf_timer_s is None:
        return {
            "status": "INCONCLUSIVE",
            "bf_expected": None,
            "clearing_time_s": clearing,
            "current_persists": current_persists,
            "notes": "50BF timer setting NOT AVAILABLE — cannot decide BF expect",
        }

    if current_persists or (clearing is not None and clearing > float(bf_timer_s)):
        expect = True
        note = "Current persists past BF timer — BF operate expected"
    elif clearing is not None and clearing <= float(bf_timer_s):
        expect = False
        note = "Current interrupted within BF timer — BF should not operate"
    else:
        return {
            "status": "INCONCLUSIVE",
            "bf_expected": None,
            "clearing_time_s": clearing,
            "bf_timer_s": float(bf_timer_s),
            "current_persists": current_persists,
            "notes": "Insufficient interruption evidence for BF decision",
        }
    return {
        "status": "OK",
        "bf_expected": expect,
        "clearing_time_s": clearing,
        "bf_timer_s": float(bf_timer_s),
        "current_persists": current_persists,
        "notes": note,
    }


def phasors_from_electrical(elec: dict[str, Any], role: str) -> Optional[complex]:
    """Resolve role → phasor from electrical analysis dict or rich flags."""
    roles = elec.get("channel_roles") or {}
    phasors = elec.get("phasors") or {}
    name = None
    for ch, r in roles.items():
        if str(r).upper() == role.upper():
            name = ch
            break
    if name and name in phasors:
        raw = phasors[name]
        if isinstance(raw, dict):
            val = raw.get("value", raw)
            return _c(val)
    # Direct role keys from enriched pipeline flags
    direct = elec.get(f"phasor_{role.upper()}") or elec.get(role.upper())
    return _c(direct)
