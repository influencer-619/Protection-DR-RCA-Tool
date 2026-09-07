"""Protection element 67 — Directional overcurrent."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_67(ProtectionElement):
    element_code = "67"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("67", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Directional overcurrent"
        return result


ELEMENT = Element_67()
