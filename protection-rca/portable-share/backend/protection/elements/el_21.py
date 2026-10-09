"""Protection element 21 — Distance with multi-zone mho/quad reach + pilot timing."""

from __future__ import annotations

from typing import Any, Optional

from protection.curves import zone_entry
from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


def _complex_z(elec: dict[str, Any]) -> Optional[complex]:
    if "apparent_z" in elec and isinstance(elec["apparent_z"], complex):
        return elec["apparent_z"]
    r = elec.get("R_ohm") or elec.get("resistance_ohm")
    x = elec.get("X_ohm") or elec.get("reactance_ohm")
    if r is not None and x is not None:
        try:
            return complex(float(r), float(x))
        except (TypeError, ValueError):
            return None
    mag = elec.get("Z_ohm") or elec.get("impedance_ohm")
    ang = elec.get("Z_angle_deg") or elec.get("impedance_angle_deg")
    if mag is not None and ang is not None:
        import math

        try:
            m = float(mag)
            a = math.radians(float(ang))
            return complex(m * math.cos(a), m * math.sin(a))
        except (TypeError, ValueError):
            return None
    return None


def _reach(settings: dict[str, Any], *keys: str) -> Optional[float]:
    for k in keys:
        v = settings.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


def _pilot_timing(timeline: list, trip_t: Optional[float]) -> dict[str, Any]:
    """POTT/PUTT-style: comm assert vs trip timing (if both present)."""
    comm_t = None
    for ev in timeline or []:
        if not isinstance(ev, dict):
            continue
        if ev.get("event_type") != "communication_signal":
            continue
        t = ev.get("t_s")
        if t is None and ev.get("timestamp") is not None:
            t = ev.get("timestamp")
        try:
            comm_t = float(t)
            break
        except (TypeError, ValueError):
            continue
    if trip_t is None or comm_t is None:
        return {
            "status": "NOT_CALCULABLE",
            "notes": "Pilot / POTT timing needs both trip and communication_signal times",
        }
    dt = float(trip_t) - float(comm_t)
    return {
        "status": "OK",
        "comm_time_s": comm_t,
        "trip_time_s": float(trip_t),
        "trip_minus_comm_s": dt,
        "pilot_consistent": abs(dt) <= 0.050,  # 50 ms typical pilot window
        "notes": "Pilot timing: trip should follow / align with carrier within ~50 ms",
    }


class Element_21(ProtectionElement):
    element_code = "21"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("21", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Distance"

        cfg = ctx.rule_config or {}
        physics = dict(cfg.get("physics") or {})
        angle = float(
            ctx.settings.get("zone_angle_deg")
            or physics.get("characteristic_angle_deg")
            or 75.0
        )
        shape = str(ctx.settings.get("zone_shape") or physics.get("shape") or "mho")
        z = _complex_z(ctx.electrical)
        obs_zone = ctx.observations.zone or 1

        reaches = {
            1: _reach(ctx.settings, "zone1_reach", "Z1_reach_ohm", "Z1", "z1mag", "z1p"),
            2: _reach(ctx.settings, "zone2_reach", "Z2_reach_ohm", "Z2", "z2mag", "z2p"),
            3: _reach(ctx.settings, "zone3_reach", "Z3_reach_ohm", "Z3", "z3mag", "z3p"),
            4: _reach(ctx.settings, "zone4_reach", "Z4_reach_ohm", "Z4", "z4mag", "z4p"),
            5: _reach(ctx.settings, "zone5_reach", "Z5_reach_ohm", "Z5", "z5mag", "z5p"),
        }
        # Nested IEC61850-style protection.21.zones.zoneN.reach_ohm
        zones_blk = ctx.settings.get("zones")
        if isinstance(zones_blk, dict):
            for zn in range(1, 6):
                if reaches[zn] is not None:
                    continue
                zb = zones_blk.get(f"zone{zn}") or zones_blk.get(zn)
                if isinstance(zb, dict):
                    reaches[zn] = _reach(zb, "reach_ohm", "reach", "PoRch", "Z")

        zone_results: dict[str, Any] = {}
        innermost_in: Optional[int] = None
        for zn, reach_f in reaches.items():
            if reach_f is None:
                continue
            ze = zone_entry(
                apparent_z_ohm=z,
                zone_reach_ohm=reach_f,
                zone_angle_deg=angle,
                shape=shape,
            )
            zone_results[f"Z{zn}"] = ze
            if ze.get("in_zone") is True and (innermost_in is None or zn < innermost_in):
                innermost_in = zn

        # Primary physics = observed zone if set, else innermost in-zone, else Z1
        use_zn = obs_zone if f"Z{obs_zone}" in zone_results else (innermost_in or 1)
        ze = zone_results.get(f"Z{use_zn}") or zone_entry(
            apparent_z_ohm=z,
            zone_reach_ohm=reaches.get(1),
            zone_angle_deg=angle,
            shape=shape,
        )

        timing = dict(result.timing or {})
        timing["zone"] = use_zn
        timing["zone_physics"] = ze
        timing["multi_zone"] = zone_results
        timing["innermost_in_zone"] = innermost_in

        trip_t = ctx.observations.trip_time_s
        timing["pilot"] = _pilot_timing(ctx.timeline, trip_t)

        if ze.get("status") == "CALCULATED" and ze.get("in_zone") is True:
            if result.enabled is True and result.expected_operation == "UNKNOWN":
                result.expected_operation = "OPERATE"
            if result.trip is False and result.enabled is True:
                result.consistency = "INCONSISTENT"
                result.metadata["zone_trip_mismatch"] = True
        elif ze.get("status") == "CALCULATED" and ze.get("in_zone") is False:
            # Trip outside all calculated zones
            any_in = any(
                (zr.get("in_zone") is True)
                for zr in zone_results.values()
                if isinstance(zr, dict)
            )
            if result.trip is True and result.enabled is True and not any_in:
                result.consistency = "INCONSISTENT"
                result.metadata["out_of_zone_trip"] = True
            elif result.expected_operation == "UNKNOWN" and not any_in:
                result.expected_operation = "NOT_OPERATE"

        if ze.get("status") == "NOT_CALCULABLE":
            result.metadata["fault_distance"] = "NOT_CALCULABLE"
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-21-NOT_CALCULABLE"]
        else:
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-21-ZONE"]

        result.timing = timing
        result.metadata["physics"] = {
            "method": ze.get("method"),
            "algorithm_version": "1.2.0",
            "zone_entry": ze,
            "multi_zone": zone_results,
            "zones_configured": sorted(zone_results.keys()),
            "pilot": timing.get("pilot"),
        }
        return result


ELEMENT = Element_21()
