"""Protection element 48 — Incomplete sequence / stall / prolonged start."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_48(ProtectionElement):
    element_code = "48"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("48", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Incomplete sequence / stall / prolonged start"
        return result


ELEMENT = Element_48()
