"""Protection element 87G — Generator differential."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_87G(ProtectionElement):
    element_code = "87G"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("87G", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Generator differential"
        return result


ELEMENT = Element_87G()
