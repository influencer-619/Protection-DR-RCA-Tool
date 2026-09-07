"""Protection element 78 — Out-of-step / phase-angle / loss-of-mains related."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_78(ProtectionElement):
    element_code = "78"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        result = base_assess("78", ctx, electrical_fault_hint=False)
        result.metadata["description"] = "Out-of-step / phase-angle measuring"
        result.metadata["note"] = (
            "Out-of-step operate not inferred from shunt-fault flags; requires digitals/settings"
        )
        return result


ELEMENT = Element_78()
