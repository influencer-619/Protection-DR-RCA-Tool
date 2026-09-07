"""Protection element 51P — Phase time overcurrent."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_51P(ProtectionElement):
    element_code = "51P"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("51P", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Phase time overcurrent"
        return result


ELEMENT = Element_51P()
