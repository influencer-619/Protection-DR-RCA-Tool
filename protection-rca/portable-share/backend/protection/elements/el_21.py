"""Protection element 21 — Distance with mho/quad zone reach."""

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


class Element_21(ProtectionElement):
    element_code = "21"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("21", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Distance"

        cfg = ctx.rule_config or {}
        physics = dict(cfg.get("physics") or {})
        reach = ctx.settings.get("zone1_reach") or ctx.settings.get("Z1_reach_ohm")
        try:
            reach_f = float(reach) if reach is not None else None
        except (TypeError, ValueError):
            reach_f = None

        z = _complex_z(ctx.electrical)
        zone = ctx.observations.zone or 1
        angle = float(
            ctx.settings.get("zone_angle_deg")
            or physics.get("characteristic_angle_deg")
            or 75.0
        )
        shape = str(ctx.settings.get("zone_shape") or physics.get("shape") or "mho")

        ze = zone_entry(
            apparent_z_ohm=z,
            zone_reach_ohm=reach_f,
            zone_angle_deg=angle,
            shape=shape,
        )

        timing = dict(result.timing or {})
        timing["zone"] = zone
        timing["zone_physics"] = ze
        if ze.get("status") == "CALCULATED" and ze.get("in_zone") is True:
            if result.enabled is True and result.expected_operation == "UNKNOWN":
                result.expected_operation = "OPERATE"
            # Observed trip should align with in-zone when both known
            if result.trip is False and result.enabled is True:
                result.consistency = "INCONSISTENT"
                result.metadata["zone_trip_mismatch"] = True
        elif ze.get("status") == "CALCULATED" and ze.get("in_zone") is False:
            if result.trip is True and result.enabled is True:
                # Trip outside zone — inconsistent unless other zones
                result.consistency = "INCONSISTENT"
                result.metadata["out_of_zone_trip"] = True
            elif result.expected_operation == "UNKNOWN":
                result.expected_operation = "NOT_OPERATE"

        if ze.get("status") == "NOT_CALCULABLE":
            result.metadata["fault_distance"] = "NOT_CALCULABLE"
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-21-NOT_CALCULABLE"]
        else:
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-21-ZONE"]

        result.timing = timing
        result.metadata["physics"] = {
            "method": ze.get("method"),
            "algorithm_version": "1.0.0",
            "zone_entry": ze,
        }
        return result


ELEMENT = Element_21()
