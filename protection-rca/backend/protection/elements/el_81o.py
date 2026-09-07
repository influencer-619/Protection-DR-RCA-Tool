"""Protection element 81O — Overfrequency."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_81O(ProtectionElement):
    element_code = "81O"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("81O", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Overfrequency"
        return result


ELEMENT = Element_81O()
