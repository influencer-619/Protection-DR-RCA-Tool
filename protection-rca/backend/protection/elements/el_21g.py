"""Protection element 21G — Ground distance."""

from __future__ import annotations

from protection.elements.el_21 import Element_21
from protection.models import ElementContext, ProtectionAssessment


class Element_21G(Element_21):
    element_code = "21G"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        result = super().assess(ctx)
        result.element = "21G"
        result.metadata["description"] = "Ground distance"
        return result


ELEMENT = Element_21G()
