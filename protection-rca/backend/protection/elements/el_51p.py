"""Protection element 51P — Phase time overcurrent (reuses 51 inverse-time physics)."""

from __future__ import annotations

from protection.elements.el_51 import Element_51
from protection.models import ElementContext, ProtectionAssessment, ProtectionElement


class Element_51P(ProtectionElement):
    element_code = "51P"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        result = Element_51().assess(ctx)
        result.element = "51P"
        result.metadata["description"] = "Phase time overcurrent"
        phys = dict(result.metadata.get("physics") or {})
        phys["variant"] = "51P"
        result.metadata["physics"] = phys
        return result


ELEMENT = Element_51P()
