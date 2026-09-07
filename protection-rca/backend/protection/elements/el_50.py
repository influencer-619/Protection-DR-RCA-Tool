"""Protection element 50 — Instantaneous overcurrent."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_50(ProtectionElement):
    element_code = "50"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("50", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Instantaneous overcurrent"
        return result


ELEMENT = Element_50()
