"""Protection element 21P — Phase distance."""

from __future__ import annotations

from protection.elements.el_21 import Element_21
from protection.models import ElementContext, ProtectionAssessment


class Element_21P(Element_21):
    element_code = "21P"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        result = super().assess(ctx)
        result.element = "21P"
        result.metadata["description"] = "Phase distance"
        return result


ELEMENT = Element_21P()
