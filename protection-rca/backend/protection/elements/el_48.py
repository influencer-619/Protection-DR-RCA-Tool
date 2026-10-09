"""Protection element 48 — Incomplete sequence / stall / prolonged start."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import apply_operate_expect, instantaneous_overcurrent, measurand_current_a


class Element_48(ProtectionElement):
    element_code = "48"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        # Motor stall: prolonged high current during start — use I vs stall pickup when set.
        # Do not treat general shunt fault_indicated as 48 operate.
        pickup = (
            ctx.settings.get("pickup_current")
            or ctx.settings.get("stall_current")
            or ctx.settings.get("pickup")
        )
        try:
            pickup_f = float(pickup) if pickup is not None else None
        except (TypeError, ValueError):
            pickup_f = None
        current = measurand_current_a(ctx.electrical)
        phys = instantaneous_overcurrent(current_a=current, pickup_a=pickup_f)
        phys["quantity"] = "I_start_stall"
        fault_hint = bool(phys.get("operate_expected") is True)
        if phys.get("status") != "OK" and ctx.observations.trip is True:
            fault_hint = True
        elif ctx.electrical.get("motor_start") and ctx.observations.trip is not True:
            fault_hint = False

        result = base_assess("48", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Incomplete sequence / stall / prolonged start"
        result.metadata["physics"] = phys
        apply_operate_expect(result, phys)
        return result


ELEMENT = Element_48()
