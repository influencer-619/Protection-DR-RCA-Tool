"""Protection element 67P — Phase directional overcurrent."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_67P(ProtectionElement):
    element_code = "67P"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("67P", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Phase directional overcurrent"
        return result


ELEMENT = Element_67P()
