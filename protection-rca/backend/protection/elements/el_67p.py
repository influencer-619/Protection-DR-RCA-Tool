"""Protection element 67P — Phase directional overcurrent (reuses 67 physics)."""

from __future__ import annotations

from protection.elements.el_67 import Element_67
from protection.models import ElementContext, ProtectionAssessment, ProtectionElement


class Element_67P(ProtectionElement):
    element_code = "67P"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        result = Element_67().assess(ctx)
        result.element = "67P"
        result.metadata["description"] = "Phase directional overcurrent"
        result.metadata["variant"] = "67P"
        return result


ELEMENT = Element_67P()
