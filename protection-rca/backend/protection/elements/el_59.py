"""Protection element 59 — Overvoltage."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_59(ProtectionElement):
    element_code = "59"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("59", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Overvoltage"
        return result


ELEMENT = Element_59()
