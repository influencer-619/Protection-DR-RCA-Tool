"""Protection element 51N — Time earth fault (reuses 51 inverse-time physics)."""

from __future__ import annotations

from protection.elements.el_51 import Element_51
from protection.models import ElementContext, ProtectionAssessment, ProtectionElement


class Element_51N(ProtectionElement):
    element_code = "51N"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        elec = dict(ctx.electrical or {})
        if elec.get("I_fault_a") is None:
            for k in ("I0_a", "IN_a", "I_n_a", "In_a"):
                if elec.get(k) is not None:
                    elec["I_fault_a"] = elec[k]
                    break
            else:
                # Residual from phases when available
                ia = elec.get("Ia_a") or elec.get("IA_a")
                ib = elec.get("Ib_a") or elec.get("IB_a")
                ic = elec.get("Ic_a") or elec.get("IC_a")
                try:
                    if ia is not None and ib is not None and ic is not None:
                        elec["I_fault_a"] = abs(float(ia) + float(ib) + float(ic)) / 3.0
                except (TypeError, ValueError):
                    pass
        old = ctx.electrical
        ctx.electrical = elec
        try:
            result = Element_51().assess(ctx)
        finally:
            ctx.electrical = old
        result.element = "51N"
        result.metadata["description"] = "Time earth fault"
        phys = dict(result.metadata.get("physics") or {})
        phys["variant"] = "51N"
        phys["method"] = "IEC_IEEE_inverse_time_earth"
        result.metadata["physics"] = phys
        return result


ELEMENT = Element_51N()
