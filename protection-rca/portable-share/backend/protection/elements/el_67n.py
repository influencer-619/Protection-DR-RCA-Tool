"""Protection element 67N — Directional earth fault (reuses 67 directional physics)."""

from __future__ import annotations

from protection.elements.el_67 import Element_67
from protection.models import ElementContext, ProtectionAssessment, ProtectionElement


class Element_67N(ProtectionElement):
    element_code = "67N"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        result = Element_67().assess(ctx)
        result.element = "67N"
        result.metadata["description"] = "Directional earth fault"
        result.metadata["variant"] = "67N"
        return result


ELEMENT = Element_67N()
