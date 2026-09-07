"""Protection element 68 — Power swing blocking."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_68(ProtectionElement):
    element_code = "68"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        # Blocking element — do not treat shunt fault as expected operate
        result = base_assess("68", ctx, electrical_fault_hint=False)
        result.metadata["description"] = "Power swing blocking"
        result.metadata["note"] = (
            "68 is a blocking function; assert/trip digitals are interpreted as block active"
        )
        return result


ELEMENT = Element_68()
