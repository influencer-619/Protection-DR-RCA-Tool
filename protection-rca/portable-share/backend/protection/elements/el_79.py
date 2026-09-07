"""Protection element 79 — Auto-reclose."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_79(ProtectionElement):
    element_code = "79"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("79", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Auto-reclose"
        return result


ELEMENT = Element_79()
