"""Protection element 50P — Phase instantaneous overcurrent (I ≥ pickup)."""

from __future__ import annotations

from protection.elements.el_50 import Element_50
from protection.models import ElementContext, ProtectionAssessment, ProtectionElement


class Element_50P(ProtectionElement):
    element_code = "50P"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        result = Element_50().assess(ctx)
        result.element = "50P"
        result.metadata["description"] = "Phase instantaneous overcurrent"
        phys = dict(result.metadata.get("physics") or {})
        phys["variant"] = "50P"
        result.metadata["physics"] = phys
        return result


ELEMENT = Element_50P()
