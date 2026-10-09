"""Protection element 50N — Instantaneous earth fault (I0 ≥ pickup)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import (
    apply_operate_expect,
    instantaneous_overcurrent,
    measurand_residual_a,
)


class Element_50N(ProtectionElement):
    element_code = "50N"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(
            ctx.electrical.get("fault_indicated", False)
            or ctx.electrical.get("ground")
        )
        pickup = (
            ctx.settings.get("pickup_current")
            or ctx.settings.get("pickup")
            or ctx.settings.get("I_pickup")
            or ctx.settings.get("IN_pickup")
        )
        try:
            pickup_f = float(pickup) if pickup is not None else None
        except (TypeError, ValueError):
            pickup_f = None
        i0 = measurand_residual_a(ctx.electrical)
        phys = instantaneous_overcurrent(current_a=i0, pickup_a=pickup_f)
        phys["quantity"] = "I0"
        if phys.get("operate_expected") is True:
            fault_hint = True
        elif phys.get("operate_expected") is False:
            fault_hint = False

        result = base_assess("50N", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Instantaneous earth fault"
        result.metadata["physics"] = phys
        apply_operate_expect(result, phys)
        if phys.get("status") == "OK":
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-50N-INST"]
        return result


ELEMENT = Element_50N()
