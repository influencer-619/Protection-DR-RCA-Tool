"""Protection element 87RGF — Restricted ground fault."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class Element_87RGF(ProtectionElement):
    element_code = "87RGF"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(
            ctx.electrical.get("fault_indicated", False)
            or ctx.electrical.get("ground")
            or ctx.electrical.get("I0")
        )
        result = base_assess("87RGF", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Restricted ground fault"
        return result


ELEMENT = Element_87RGF()
