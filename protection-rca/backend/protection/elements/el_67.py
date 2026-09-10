"""Protection element 67 — Directional overcurrent (polarizing-angle aware)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import directional_67, phasors_from_electrical


class Element_67(ProtectionElement):
    element_code = "67"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        mta = float(ctx.settings.get("mta_deg") or ctx.settings.get("max_torque_angle") or -45.0)
        region = float(ctx.settings.get("forward_region_deg") or 90.0)

        direction = ctx.electrical.get("direction_67")
        if not isinstance(direction, dict):
            # Prefer residual / faulted phase current vs quadrature / positive-seq voltage
            i = phasors_from_electrical(ctx.electrical, "IN") or phasors_from_electrical(
                ctx.electrical, "IA"
            )
            v = phasors_from_electrical(ctx.electrical, "VA") or phasors_from_electrical(
                ctx.electrical, "VB"
            )
            direction = directional_67(
                i_fault=i,
                v_polarize=v,
                forward_region_deg=region,
                max_torque_angle_deg=mta,
            )

        # Directional gate: reverse fault should not expect operate for forward-looking 67
        dir_label = direction.get("direction")
        if dir_label == "REVERSE" and direction.get("status") == "OK":
            fault_hint = False
        elif dir_label == "FORWARD" and fault_hint:
            fault_hint = True

        # Observation direction from digital if present
        if ctx.observations.direction is None and dir_label in ("FORWARD", "REVERSE"):
            ctx.observations.direction = dir_label

        result = base_assess("67", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Directional overcurrent"
        result.metadata["directional"] = direction
        if dir_label:
            result.metadata["direction"] = dir_label
        return result


ELEMENT = Element_67()
