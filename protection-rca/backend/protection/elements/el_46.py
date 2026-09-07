"""Protection element 46 — Negative-sequence / phase unbalance current."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_46(ProtectionElement):
    element_code = "46"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        i2 = ctx.electrical.get("I2") or ctx.electrical.get("i2_mag")
        fault_hint = False
        if i2 is not None:
            try:
                fault_hint = float(i2) > 0
            except (TypeError, ValueError):
                fault_hint = False
        result = base_assess("46", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Negative-sequence / phase unbalance current"
        if i2 is not None:
            result.metadata["I2"] = i2
        return result


ELEMENT = Element_46()
