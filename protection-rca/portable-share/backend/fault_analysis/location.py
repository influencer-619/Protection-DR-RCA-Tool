"""Single-ended fault location algorithms (AFAS-style).

Never invents distance: each algorithm returns OK or NOT_CALCULABLE with reason.
"""

from __future__ import annotations

import cmath
import math
from typing import Any, Optional

from electrical_analysis.analyzer import ElectricalAnalysisResult


def _phasor_complex(elec: ElectricalAnalysisResult, role: str) -> Optional[complex]:
    """Resolve channel role (IA, VA, …) to a fundamental phasor complex."""
    name = None
    for ch, r in elec.channel_roles.items():
        if str(r).upper() == role.upper():
            name = ch
            break
    if not name:
        return None
    ph = elec.phasors.get(name)
    if ph is None or ph.status != "OK" or not isinstance(ph.value, dict):
        return None
    try:
        return complex(float(ph.value["real"]), float(ph.value["imag"]))
    except (KeyError, TypeError, ValueError):
        return None


def _z_from_signal(result: Any) -> Optional[complex]:
    if result is None or getattr(result, "status", None) != "OK":
        return None
    val = getattr(result, "value", None)
    if not isinstance(val, dict):
        return None
    try:
        return complex(float(val["R"]), float(val["X"]))
    except (KeyError, TypeError, ValueError):
        return None


def normalize_line_params(line_params: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Build Z1/Z0 per-km complexes from settings line block (no invention)."""
    if not line_params:
        return {}
    out = dict(line_params)
    if "positive_sequence_impedance_ohm_per_km" not in out:
        r = line_params.get("positive_sequence_r_ohm_per_km")
        x = line_params.get("positive_sequence_x_ohm_per_km")
        if r is not None and x is not None:
            out["positive_sequence_impedance_ohm_per_km"] = complex(float(r), float(x))
    else:
        z = out["positive_sequence_impedance_ohm_per_km"]
        if not isinstance(z, complex):
            try:
                out["positive_sequence_impedance_ohm_per_km"] = complex(z)
            except (TypeError, ValueError):
                pass
    if "zero_sequence_impedance_ohm_per_km" not in out:
        r0 = line_params.get("zero_sequence_r_ohm_per_km")
        x0 = line_params.get("zero_sequence_x_ohm_per_km")
        if r0 is not None and x0 is not None:
            out["zero_sequence_impedance_ohm_per_km"] = complex(float(r0), float(x0))
    return out


def parse_ratio_value(raw: Any) -> Optional[float]:
    """Parse CT/VT ratio from number or string forms: 800, '800', '800/1', '132000/110'."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        v = float(raw)
        return v if v != 0 and math.isfinite(v) else None
    s = str(raw).strip().replace(" ", "").replace(":", "/")
    if not s:
        return None
    if "/" in s:
        left, _, right = s.partition("/")
        try:
            a, b = float(left), float(right)
        except ValueError:
            return None
        if b == 0 or not math.isfinite(a) or not math.isfinite(b):
            return None
        return a / b
    try:
        v = float(s)
    except ValueError:
        return None
    return v if v != 0 and math.isfinite(v) else None


def normalize_ct_vt(ct_vt: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not ct_vt:
        return {}
    out = dict(ct_vt)

    # Prefer explicit primary/secondary when present
    if out.get("ct_ratio") in (None, "", "NOT VERIFIED"):
        cp, cs = ct_vt.get("ct_primary_a"), ct_vt.get("ct_secondary_a")
        if cp is not None and cs is not None and float(cs) != 0:
            out["ct_ratio"] = float(cp) / float(cs)
    if out.get("vt_ratio") in (None, "", "NOT VERIFIED"):
        vp, vs = ct_vt.get("vt_primary_v"), ct_vt.get("vt_secondary_v")
        if vp is not None and vs is not None and float(vs) != 0:
            out["vt_ratio"] = float(vp) / float(vs)

    # Accept vendor strings such as "800/1" or "132000/110"
    cr = parse_ratio_value(out.get("ct_ratio"))
    if cr is not None:
        out["ct_ratio"] = cr
    else:
        out.pop("ct_ratio", None)
    vr = parse_ratio_value(out.get("vt_ratio"))
    if vr is not None:
        out["vt_ratio"] = vr
    else:
        out.pop("vt_ratio", None)

    # Fill primary/secondary from slash form when only ratio string was given
    raw_ct = ct_vt.get("ct_ratio")
    if isinstance(raw_ct, str) and "/" in raw_ct and "ct_primary_a" not in out:
        left, _, right = str(raw_ct).replace(" ", "").partition("/")
        try:
            out["ct_primary_a"] = float(left)
            out["ct_secondary_a"] = float(right)
        except ValueError:
            pass
    raw_vt = ct_vt.get("vt_ratio")
    if isinstance(raw_vt, str) and "/" in raw_vt and "vt_primary_v" not in out:
        left, _, right = str(raw_vt).replace(" ", "").partition("/")
        try:
            out["vt_primary_v"] = float(left)
            out["vt_secondary_v"] = float(right)
        except ValueError:
            pass
    return out


def _loop_impedance(
    elec: ElectricalAnalysisResult, fault_type: str
) -> tuple[Optional[complex], str]:
    """Pick loop Z for the classified fault type (PP delta preferred over phase self-Z)."""
    ft = (fault_type or "").upper()
    # Distance R–X / location: use the faulted loop, not a random phase V/I.
    preferred: list[str] = []
    if ft in ("AG",):
        preferred = ["loop_AG", "phase_A"]
    elif ft in ("BG",):
        preferred = ["loop_BG", "phase_B"]
    elif ft in ("CG",):
        preferred = ["loop_CG", "phase_C"]
    elif ft in ("AB", "ABG"):
        preferred = ["loop_AB", "phase_A", "phase_B"]
    elif ft in ("BC", "BCG"):
        preferred = ["loop_BC", "phase_B", "phase_C"]
    elif ft in ("CA", "CAG"):
        preferred = ["loop_CA", "phase_C", "phase_A"]
    elif ft in ("ABC", "ABCG"):
        preferred = ["loop_AB", "phase_A", "phase_B", "phase_C"]
    else:
        preferred = ["phase_A", "phase_B", "phase_C"]

    for key in preferred:
        z = _z_from_signal(elec.impedance.get(key))
        if z is not None:
            return z, key
    # Fallback any available impedance
    for key, payload in (elec.impedance or {}).items():
        z = _z_from_signal(payload)
        if z is not None:
            return z, str(key)
    return None, "none"


def _row(
    *,
    algorithm: str,
    status: str,
    distance_km: Optional[float] = None,
    distance_pct: Optional[float] = None,
    notes: str = "",
    unit: str = "km",
) -> dict[str, Any]:
    return {
        "algorithm": algorithm,
        "status": status,
        "distance_km": distance_km,
        "distance_pct": distance_pct,
        "unit": unit,
        "notes": notes,
    }


def _pct(dist: Optional[float], length: Optional[float]) -> Optional[float]:
    if dist is None or length is None or float(length) <= 0:
        return None
    return float(dist) / float(length) * 100.0


def locate_reactance(
    z_loop: Optional[complex],
    z1_per_km: Optional[complex],
    length_km: Optional[float],
) -> dict[str, Any]:
    name = "Single-End Reactance"
    if z_loop is None:
        return _row(algorithm=name, status="NOT_CALCULABLE", notes="Loop impedance NOT AVAILABLE")
    if z1_per_km is None or abs(z1_per_km.imag) < 1e-12:
        return _row(
            algorithm=name,
            status="NOT_CALCULABLE",
            notes="Line X1 per km NOT AVAILABLE or near zero",
        )
    dist = z_loop.imag / z1_per_km.imag
    if dist < 0:
        return _row(
            algorithm=name,
            status="INCONCLUSIVE",
            distance_km=float(dist),
            distance_pct=_pct(dist, length_km),
            notes="Negative reactance distance (check CT/VT polarity or window)",
        )
    return _row(
        algorithm=name,
        status="OK",
        distance_km=float(dist),
        distance_pct=_pct(dist, length_km),
        notes="d = Im(Zloop) / Im(Z1/km)",
    )


def locate_apparent_z(
    z_loop: Optional[complex],
    z1_per_km: Optional[complex],
    length_km: Optional[float],
) -> dict[str, Any]:
    name = "Single-End Apparent |Z|/|Z1|"
    if z_loop is None:
        return _row(algorithm=name, status="NOT_CALCULABLE", notes="Loop impedance NOT AVAILABLE")
    if z1_per_km is None or abs(z1_per_km) < 1e-12:
        return _row(algorithm=name, status="NOT_CALCULABLE", notes="Line Z1 per km NOT AVAILABLE")
    dist = abs(z_loop / z1_per_km)
    note = "d = |Zapp| / |Z1/km|"
    if length_km is not None and dist > float(length_km) * 1.5:
        return _row(
            algorithm=name,
            status="INCONCLUSIVE",
            distance_km=float(dist),
            distance_pct=_pct(dist, length_km),
            notes=note + " — exceeds 1.5× line length",
        )
    return _row(
        algorithm=name,
        status="OK",
        distance_km=float(dist),
        distance_pct=_pct(dist, length_km),
        notes=note,
    )


def locate_takagi(
    elec: ElectricalAnalysisResult,
    fault_type: str,
    z1_per_km: Optional[complex],
    length_km: Optional[float],
) -> dict[str, Any]:
    """Classic single-end Takagi for SLG: d = Re(V * conj(I0)) / Re(Z1 * I * conj(I0))."""
    name = "Single-End Takagi"
    ft = (fault_type or "").upper()
    phase = {"AG": "A", "BG": "B", "CG": "C"}.get(ft)
    if phase is None:
        return _row(
            algorithm=name,
            status="NOT_CALCULABLE",
            notes=f"Takagi SLG form requires AG/BG/CG (got {fault_type or 'UNKNOWN'})",
        )
    if z1_per_km is None or abs(z1_per_km) < 1e-12:
        return _row(algorithm=name, status="NOT_CALCULABLE", notes="Line Z1 per km NOT AVAILABLE")

    v = _phasor_complex(elec, f"V{phase}")
    i = _phasor_complex(elec, f"I{phase}")
    # I0 from sequences or (Ia+Ib+Ic)/3
    i0 = None
    seq = elec.sequences.get("current_sequences")
    if seq is not None and seq.status == "OK" and isinstance(seq.value, dict):
        zc = seq.value.get("zero") or {}
        if "real" in zc and "imag" in zc:
            try:
                i0 = complex(float(zc["real"]), float(zc["imag"]))
            except (TypeError, ValueError):
                i0 = None
        elif "magnitude" in zc and "angle_deg" in zc:
            import cmath
            import math

            try:
                i0 = cmath.rect(
                    float(zc["magnitude"]), math.radians(float(zc["angle_deg"]))
                )
            except (TypeError, ValueError):
                i0 = None
    if i0 is None:
        ia, ib, ic = (
            _phasor_complex(elec, "IA"),
            _phasor_complex(elec, "IB"),
            _phasor_complex(elec, "IC"),
        )
        if ia is not None and ib is not None and ic is not None:
            i0 = (ia + ib + ic) / 3.0

    if v is None or i is None or i0 is None:
        return _row(
            algorithm=name,
            status="NOT_CALCULABLE",
            notes="V, I, or I0 phasors NOT AVAILABLE for Takagi",
        )
    if abs(i0) < 1e-9:
        return _row(algorithm=name, status="NOT_CALCULABLE", notes="I0 near zero — Takagi not calculable")

    num = (v * i0.conjugate()).real
    den = ((z1_per_km * i) * i0.conjugate()).real
    if abs(den) < 1e-12:
        return _row(algorithm=name, status="NOT_CALCULABLE", notes="Takagi denominator near zero")
    dist = num / den
    return _row(
        algorithm=name,
        status="OK" if dist >= 0 else "INCONCLUSIVE",
        distance_km=float(dist),
        distance_pct=_pct(dist, length_km),
        notes="d = Re(V·I0*) / Re(Z1·I·I0*) (SLG Takagi)",
    )


def estimate_line_impedance_from_settings(line: dict[str, Any]) -> dict[str, Any]:
    """Report positive/zero sequence from settings (estimation sheet baseline)."""
    z1 = line.get("positive_sequence_impedance_ohm_per_km")
    z0 = line.get("zero_sequence_impedance_ohm_per_km")
    out: dict[str, Any] = {
        "status": "OK" if z1 is not None else "NOT_AVAILABLE",
        "source": "settings_line_block",
        "length_km": line.get("length_km"),
    }
    if isinstance(z1, complex):
        out["z1_ohm_per_km"] = {"R": z1.real, "X": z1.imag, "magnitude": abs(z1)}
    if isinstance(z0, complex):
        out["z0_ohm_per_km"] = {"R": z0.real, "X": z0.imag, "magnitude": abs(z0)}
    return out


def locate_two_ended(
    elec_local: ElectricalAnalysisResult,
    elec_remote: ElectricalAnalysisResult,
    *,
    fault_type: str,
    z1_per_km: Optional[complex],
    length_km: Optional[float],
    sync_offset_us: Optional[float] = None,
) -> dict[str, Any]:
    """
    Two-ended reactance / current-weighted location (simplified AFAS form).

    Uses local and remote loop currents with line Z1:
      d ≈ Im(V_L / I_L) / Im(Z1/km)  blended with remote-end estimate.
    Requires clock alignment note when sync_offset_us is unknown.
    """
    name = "Two-Ended Current-Weighted"
    if z1_per_km is None or abs(z1_per_km) < 1e-12:
        return _row(algorithm=name, status="NOT_CALCULABLE", notes="Line Z1 per km NOT AVAILABLE")
    if length_km is None or float(length_km) <= 0:
        return _row(algorithm=name, status="NOT_CALCULABLE", notes="Line length NOT AVAILABLE")

    z_l, _ = _loop_impedance(elec_local, fault_type)
    z_r, _ = _loop_impedance(elec_remote, fault_type)
    i_l = (
        _phasor_complex(elec_local, "IA")
        or _phasor_complex(elec_local, "IB")
        or _phasor_complex(elec_local, "IC")
    )
    i_r = (
        _phasor_complex(elec_remote, "IA")
        or _phasor_complex(elec_remote, "IB")
        or _phasor_complex(elec_remote, "IC")
    )
    if z_l is None or z_r is None:
        return _row(
            algorithm=name,
            status="NOT_CALCULABLE",
            notes="Local and remote loop impedances required",
        )
    if i_l is None or i_r is None or (abs(i_l) + abs(i_r)) < 1e-9:
        return _row(
            algorithm=name,
            status="NOT_CALCULABLE",
            notes="Local and remote fault currents required",
        )

    # Distance from each end via reactance, then current-magnitude weight
    d_l = z_l.imag / z1_per_km.imag if abs(z1_per_km.imag) > 1e-12 else abs(z_l / z1_per_km)
    d_r = z_r.imag / z1_per_km.imag if abs(z1_per_km.imag) > 1e-12 else abs(z_r / z1_per_km)
    # Remote-end distance is from remote terminal; convert to local-referenced
    d_r_from_local = float(length_km) - float(d_r)
    w_l = abs(i_l)
    w_r = abs(i_r)
    dist = (w_l * float(d_l) + w_r * float(d_r_from_local)) / (w_l + w_r)

    notes = "d = weighted mean of local & remote reactance distances"
    if sync_offset_us is None:
        notes += " — clock sync offset NOT VERIFIED"
        status = "INCONCLUSIVE" if dist >= 0 else "NOT_CALCULABLE"
    else:
        notes += f" — sync_offset_us={float(sync_offset_us):.1f}"
        status = "OK" if dist >= 0 else "INCONCLUSIVE"

    return _row(
        algorithm=name,
        status=status,
        distance_km=float(dist),
        distance_pct=_pct(dist, length_km),
        notes=notes,
    )


def compute_fault_locations(
    elec: ElectricalAnalysisResult,
    *,
    fault_type: str,
    line_params: Optional[dict[str, Any]] = None,
    ct_vt_ratios: Optional[dict[str, Any]] = None,
    elec_remote: Optional[ElectricalAnalysisResult] = None,
    sync_offset_us: Optional[float] = None,
) -> dict[str, Any]:
    """Run AFAS-style location suite. Prefer first OK row for primary distance."""
    line = normalize_line_params(line_params)
    ct_vt = normalize_ct_vt(ct_vt_ratios)
    z1 = line.get("positive_sequence_impedance_ohm_per_km")
    if isinstance(z1, (int, float)):
        z1 = complex(z1)
    length = line.get("length_km")
    try:
        length_f = float(length) if length is not None else None
    except (TypeError, ValueError):
        length_f = None

    z_loop, loop_src = _loop_impedance(elec, fault_type)
    z1c = z1 if isinstance(z1, complex) else None
    algorithms = [
        locate_reactance(z_loop, z1c, length_f),
        locate_takagi(elec, fault_type, z1c, length_f),
        locate_apparent_z(z_loop, z1c, length_f),
    ]
    if elec_remote is not None:
        algorithms.insert(
            0,
            locate_two_ended(
                elec,
                elec_remote,
                fault_type=fault_type,
                z1_per_km=z1c,
                length_km=length_f,
                sync_offset_us=sync_offset_us,
            ),
        )

    preferred = next((a for a in algorithms if a["status"] == "OK"), None)
    if preferred is None:
        preferred = next((a for a in algorithms if a.get("distance_km") is not None), None)

    missing: list[str] = []
    if z1 is None:
        missing.append("line Z1/km")
    if not ct_vt.get("ct_ratio") or not ct_vt.get("vt_ratio"):
        # Soft note — secondary quantities may already be primary-scaled in COMTRADE
        pass
    if z_loop is None:
        missing.append("measured loop impedance")

    primary_status = preferred["status"] if preferred else "NOT_CALCULABLE"
    reason = None
    if primary_status != "OK":
        reason = (
            "FAULT DISTANCE: NOT CALCULABLE. REASON: "
            + (
                ", ".join(missing)
                if missing
                else (preferred or {}).get("notes")
                or "Insufficient verified inputs"
            )
        )

    loop_impedance: dict[str, Any] | None = None
    if z_loop is not None:
        mag = abs(z_loop)
        ang = math.degrees(cmath.phase(z_loop))
        loop_impedance = {
            "R_ohm": float(z_loop.real),
            "X_ohm": float(z_loop.imag),
            "magnitude_ohm": float(mag),
            "angle_deg": float(ang),
            "source": loop_src,
        }

    value_km = preferred.get("distance_km") if preferred else None
    if isinstance(value_km, float):
        value_km = round(value_km, 6)

    return {
        "status": primary_status if preferred else "NOT_CALCULABLE",
        "value_km": value_km,
        "method": preferred.get("algorithm") if preferred else None,
        "unit": "km",
        "loop_source": loop_src,
        "loop_impedance": loop_impedance,
        "algorithms": algorithms,
        "line_impedance_estimate": estimate_line_impedance_from_settings(line),
        "reason": reason,
        "two_ended": elec_remote is not None,
        "sync_offset_us": sync_offset_us,
    }
