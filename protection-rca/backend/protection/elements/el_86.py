"""Protection element 86 — Lockout."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_86(ProtectionElement):
    element_code = "86"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("86", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Lockout"
        return result


ELEMENT = Element_86()
