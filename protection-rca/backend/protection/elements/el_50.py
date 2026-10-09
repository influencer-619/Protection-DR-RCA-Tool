"""Protection element 50 — Instantaneous overcurrent (I ≥ pickup)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import (
    apply_operate_expect,
    instantaneous_overcurrent,
    measurand_current_a,
)


class Element_50(ProtectionElement):
    element_code = "50"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        pickup = (
            ctx.settings.get("pickup_current")
            or ctx.settings.get("pickup")
            or ctx.settings.get("I_pickup")
        )
        try:
            pickup_f = float(pickup) if pickup is not None else None
        except (TypeError, ValueError):
            pickup_f = None
        current = measurand_current_a(ctx.electrical)
        phys = instantaneous_overcurrent(current_a=current, pickup_a=pickup_f)
        if phys.get("operate_expected") is True:
            fault_hint = True
        elif phys.get("operate_expected") is False:
            fault_hint = False

        result = base_assess("50", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Instantaneous overcurrent"
        result.metadata["physics"] = phys
        apply_operate_expect(result, phys)
        if phys.get("status") == "OK":
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-50-INST"]
        return result


ELEMENT = Element_50()
