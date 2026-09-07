"""Protection element 87L — Line differential."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_87L(ProtectionElement):
    element_code = "87L"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("87L", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Line differential"
        return result


ELEMENT = Element_87L()
