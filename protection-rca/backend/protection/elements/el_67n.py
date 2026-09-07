"""Protection element 67N — Directional earth fault."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_67N(ProtectionElement):
    element_code = "67N"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("67N", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Directional earth fault"
        return result


ELEMENT = Element_67N()
