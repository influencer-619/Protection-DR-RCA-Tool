"""Protection element 49 — Thermal overload."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_49(ProtectionElement):
    element_code = "49"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("49", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Thermal overload"
        return result


ELEMENT = Element_49()
