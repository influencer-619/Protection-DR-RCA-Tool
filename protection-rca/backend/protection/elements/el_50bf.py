"""Protection element 50BF — Breaker failure."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_50BF(ProtectionElement):
    element_code = "50BF"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("50BF", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Breaker failure"
        return result


ELEMENT = Element_50BF()
