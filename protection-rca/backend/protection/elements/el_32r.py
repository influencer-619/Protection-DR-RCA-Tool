"""Protection element 32R — Reverse power / directional power (reverse)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_32R(ProtectionElement):
    element_code = "32R"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        # Reverse-power trips are not inferred from shunt-fault flags alone
        result = base_assess("32R", ctx, electrical_fault_hint=False)
        result.metadata["description"] = "Reverse power"
        result.metadata["note"] = (
            "Operate expectation requires verified reverse-power settings and power sign; "
            "not inferred from shunt-fault indication alone"
        )
        return result


ELEMENT = Element_32R()
