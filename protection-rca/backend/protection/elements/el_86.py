"""Protection element 86 — Lockout (scheme status — not a fault detector)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_86(ProtectionElement):
    element_code = "86"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        result = base_assess("86", ctx, electrical_fault_hint=False)
        result.metadata["description"] = "Lockout"
        result.metadata["physics"] = {
            "status": "SCHEME",
            "operate_expected": None,
            "notes": "86 lockout follows BF/diff trip schemes — not a primary fault detector",
        }
        if result.expected_operation == "OPERATE" and ctx.observations.trip is not True:
            result.expected_operation = "UNKNOWN"
        return result


ELEMENT = Element_86()
