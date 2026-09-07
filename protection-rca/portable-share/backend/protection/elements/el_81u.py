"""Protection element 81U — Underfrequency."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_81U(ProtectionElement):
    element_code = "81U"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("81U", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Underfrequency"
        return result


ELEMENT = Element_81U()
