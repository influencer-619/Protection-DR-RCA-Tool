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


def instantaneous_overcurrent(
    *,
    current_a: Optional[float],
    pickup_a: Optional[float],
) -> dict[str, Any]:
    """ANSI 50 / 50P: operate expected when |I| ≥ pickup (no intentional delay)."""
    if current_a is None or pickup_a is None:
        return {
            "status": "NOT_CALCULABLE",
            "operate_expected": None,
            "current_a": current_a,
            "pickup_a": pickup_a,
            "notes": "Measured current and pickup setting required",
        }
    try:
        i = float(current_a)
        pu = float(pickup_a)
    except (TypeError, ValueError):
        return {
            "status": "NOT_CALCULABLE",
            "operate_expected": None,
            "notes": "Invalid current or pickup",
        }
    if pu <= 0:
        return {
            "status": "NOT_CALCULABLE",
            "operate_expected": None,
            "notes": "Pickup must be > 0",
        }
    return {
        "status": "OK",
        "operate_expected": bool(i >= pu),
        "current_a": i,
        "pickup_a": pu,
        "multiple": i / pu,
        "notes": "Instantaneous OC: trip expected if I ≥ Ip",
    }


def threshold_compare(
    *,
    measured: Optional[float],
    pickup: Optional[float],
    mode: str,
    unit: str = "",
) -> dict[str, Any]:
    """Under/over threshold for 27/59/81 (mode = under | over)."""
    if measured is None or pickup is None:
        return {
            "status": "NOT_CALCULABLE",
            "operate_expected": None,
            "measured": measured,
            "pickup": pickup,
            "mode": mode,
            "unit": unit,
            "notes": f"Measured value and pickup required ({unit or 'eu'})",
        }
    try:
        m = float(measured)
        p = float(pickup)
    except (TypeError, ValueError):
        return {
            "status": "NOT_CALCULABLE",
            "operate_expected": None,
            "mode": mode,
            "notes": "Invalid measured or pickup",
        }
    mode_l = str(mode or "").lower()
    if mode_l == "under":
        expect = m <= p
        note = f"Under-threshold: operate if measured ≤ pickup ({unit})"
    else:
        expect = m >= p
        note = f"Over-threshold: operate if measured ≥ pickup ({unit})"
    return {
        "status": "OK",
        "operate_expected": bool(expect),
        "measured": m,
        "pickup": p,
        "mode": mode_l,
        "unit": unit,
        "notes": note,
    }


def measurand_current_a(elec: dict[str, Any]) -> Optional[float]:
    """Best available phase/fault current magnitude from electrical flags."""
    for k in ("I_fault_a", "I_max_a", "current_a", "I_peak_a"):
        v = elec.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    vals: list[float] = []
    for k in ("Ia", "Ib", "Ic"):
        v = elec.get(k)
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return max(vals) if vals else None


def measurand_residual_a(elec: dict[str, Any]) -> Optional[float]:
    for k in ("I0_a", "IN_a", "I_n_a", "In_a", "I0"):
        v = elec.get(k)
        if v is None:
            continue
        try:
            return abs(float(v))
        except (TypeError, ValueError):
            continue
    ia, ib, ic = elec.get("Ia"), elec.get("Ib"), elec.get("Ic")
    try:
        if ia is not None and ib is not None and ic is not None:
            return abs(float(ia) + float(ib) + float(ic)) / 3.0
    except (TypeError, ValueError):
        pass
    return None


def measurand_voltage_v(elec: dict[str, Any]) -> Optional[float]:
    for k in ("V_min_v", "V_fault_v", "voltage_v", "V_a"):
        v = elec.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    vals: list[float] = []
    for k in ("Va", "Vb", "Vc", "Vab", "Vbc", "Vca"):
        v = elec.get(k)
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return min(vals) if vals else None


def measurand_voltage_max_v(elec: dict[str, Any]) -> Optional[float]:
    for k in ("V_max_v", "V_over_v"):
        v = elec.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    vals: list[float] = []
    for k in ("Va", "Vb", "Vc", "Vab", "Vbc", "Vca"):
        v = elec.get(k)
        if v is None:
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return max(vals) if vals else None


def measurand_frequency_hz(elec: dict[str, Any]) -> Optional[float]:
    for k in ("frequency_hz", "f_hz", "freq_hz"):
        v = elec.get(k)
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    return None


def thermal_i2t(
    *,
    current_a: Optional[float],
    flc_a: Optional[float],
    tau_s: Optional[float] = None,
    duration_s: Optional[float] = None,
    trip_threshold_pu: float = 1.05,
) -> dict[str, Any]:
    """ANSI 49 simplified thermal model: heating ∝ (I/Iflc)² · t.

    When duration is unknown, operate expected if I ≥ trip_threshold · Iflc
    (sustained overload indication from the DR window).
    """
    if current_a is None or flc_a is None:
        return {
            "status": "NOT_CALCULABLE",
            "operate_expected": None,
            "notes": "Measured current and full-load / thermal pickup required",
        }
    try:
        i = float(current_a)
        flc = float(flc_a)
    except (TypeError, ValueError):
        return {"status": "NOT_CALCULABLE", "operate_expected": None, "notes": "Invalid I or Iflc"}
    if flc <= 0:
        return {"status": "NOT_CALCULABLE", "operate_expected": None, "notes": "Iflc must be > 0"}
    multiple = i / flc
    tau = float(tau_s) if tau_s is not None else 60.0
    dur = float(duration_s) if duration_s is not None else None
    # Relative thermal state proxy (0…1+): 1 − exp(−(I/In)² · t / τ)
    if dur is not None and dur > 0:
        thermal_state = 1.0 - math.exp(-(multiple**2) * dur / max(tau, 1e-6))
        expect = thermal_state >= 0.95 or multiple >= trip_threshold_pu
    else:
        thermal_state = None
        expect = multiple >= trip_threshold_pu
    return {
        "status": "OK",
        "operate_expected": bool(expect),
        "current_a": i,
        "flc_a": flc,
        "multiple": multiple,
        "tau_s": tau,
        "duration_s": dur,
        "thermal_state": thermal_state,
        "notes": "49 thermal: state ≈ 1−exp(−(I/Iflc)²·t/τ); trip if overloaded",
    }


def sync_check_25(
    *,
    v_bus: Optional[complex] = None,
    v_line: Optional[complex] = None,
    f_bus_hz: Optional[float] = None,
    f_line_hz: Optional[float] = None,
    dv_max_pu: float = 0.05,
    df_max_hz: float = 0.2,
    dphi_max_deg: float = 20.0,
    v_nom: float = 1.0,
) -> dict[str, Any]:
    """ANSI 25 synchronism check: ΔV, Δf, Δφ within close limits → permit."""
    if v_bus is None or v_line is None:
        return {
            "status": "NOT_CALCULABLE",
            "permit_close": None,
            "notes": "Bus and line voltage phasors required for sync-check",
        }
    try:
        vb = complex(v_bus)
        vl = complex(v_line)
    except (TypeError, ValueError):
        return {
            "status": "NOT_CALCULABLE",
            "permit_close": None,
            "notes": "Invalid sync-check phasors",
        }
    if abs(vb) < 1e-9 or abs(vl) < 1e-9:
        return {
            "status": "NOT_CALCULABLE",
            "permit_close": None,
            "notes": "Near-zero voltage — sync-check not calculable",
        }
    nom = abs(v_nom) if v_nom else max(abs(vb), abs(vl))
    dv_pu = abs(abs(vb) - abs(vl)) / max(nom, 1e-9)
    dphi = math.degrees(cmath.phase(vb) - cmath.phase(vl))
    while dphi > 180:
        dphi -= 360
    while dphi < -180:
        dphi += 360
    df = None
    if f_bus_hz is not None and f_line_hz is not None:
        try:
            df = abs(float(f_bus_hz) - float(f_line_hz))
        except (TypeError, ValueError):
            df = None
    ok_v = dv_pu <= dv_max_pu
    ok_phi = abs(dphi) <= dphi_max_deg
    ok_f = True if df is None else df <= df_max_hz
    permit = bool(ok_v and ok_phi and ok_f)
    return {
        "status": "OK",
        "permit_close": permit,
        "operate_expected": permit,  # "operate" = sync permit assert
        "dv_pu": float(dv_pu),
        "dphi_deg": float(dphi),
        "df_hz": df,
        "limits": {"dv_max_pu": dv_max_pu, "df_max_hz": df_max_hz, "dphi_max_deg": dphi_max_deg},
        "notes": "25 sync-check: permit close when ΔV, Δf, Δφ within limits",
    }


def apply_operate_expect(
    result: Any,
    physics: dict[str, Any],
) -> None:
    """Update expected_operation from physics operate_expected when enabled."""
    if not isinstance(physics, dict):
        return
    if physics.get("status") != "OK":
        return
    expect = physics.get("operate_expected")
    if expect is None:
        return
    if result.enabled is False:
        return
    if expect is True and result.expected_operation in ("UNKNOWN", "NOT_OPERATE"):
        result.expected_operation = "OPERATE"
    elif expect is False and result.trip is not True:
        result.expected_operation = "NOT_OPERATE"


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
