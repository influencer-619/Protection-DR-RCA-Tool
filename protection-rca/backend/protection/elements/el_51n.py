"""Protection element 51N — Time earth fault."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_51N(ProtectionElement):
    element_code = "51N"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("51N", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Time earth fault"
        return result


ELEMENT = Element_51N()
