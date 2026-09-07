"""Protection element 25 — Synchronism check."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_25(ProtectionElement):
    element_code = "25"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("25", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Synchronism check"
        return result


ELEMENT = Element_25()
