"""Protection element 87G — Generator differential (operate/restraint)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import _c, differential_operate_restraint


class Element_87G(ProtectionElement):
    element_code = "87G"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        # Never invent operate from general fault_indicated alone — need Id/Ir or digitals.
        fault_hint = False
        slope = float(ctx.settings.get("slope") or ctx.settings.get("k") or 0.3)
        pickup = float(ctx.settings.get("pickup_a") or ctx.settings.get("Id_min") or 0.2)

        diff = ctx.electrical.get("diff_87g") or ctx.electrical.get("diff_87")
        if not isinstance(diff, dict):
            diff = differential_operate_restraint(
                i_w1=_c(ctx.electrical.get("i_w1") or ctx.electrical.get("i_gen")),
                i_w2=_c(ctx.electrical.get("i_w2") or ctx.electrical.get("i_neutral")),
                slope=slope,
                pickup_a=pickup,
            )

        if diff.get("operate_expected") is True:
            fault_hint = True
        elif diff.get("operate_expected") is False and diff.get("status") == "OK":
            fault_hint = False
        elif ctx.observations.trip is True:
            # Digital trip without calculable Id — treat as operated evidence only
            fault_hint = True

        result = base_assess("87G", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Generator differential"
        result.metadata["differential"] = diff
        if diff.get("status") == "NOT_CALCULABLE" and ctx.observations.trip is not True:
            result.expected_operation = "UNKNOWN"
            result.consistency = "UNVERIFIABLE"
        return result


ELEMENT = Element_87G()
