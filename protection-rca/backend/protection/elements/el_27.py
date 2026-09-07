"""Protection element 27 — Undervoltage."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_27(ProtectionElement):
    element_code = "27"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("27", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Undervoltage"
        return result


ELEMENT = Element_27()
