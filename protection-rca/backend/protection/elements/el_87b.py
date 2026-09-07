"""Protection element 87B — Bus differential."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_87B(ProtectionElement):
    element_code = "87B"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("87B", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Bus differential"
        return result


ELEMENT = Element_87B()
