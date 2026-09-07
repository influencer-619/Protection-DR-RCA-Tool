"""Protection element 50P — Phase instantaneous overcurrent."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_50P(ProtectionElement):
    element_code = "50P"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("50P", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Phase instantaneous overcurrent"
        return result


ELEMENT = Element_50P()
