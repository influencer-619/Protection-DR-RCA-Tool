"""Protection element 87B — Bus differential (operate/restraint aware)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import _c, differential_operate_restraint


class Element_87B(ProtectionElement):
    element_code = "87B"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        slope = float(ctx.settings.get("slope") or ctx.settings.get("k") or 0.3)
        pickup = float(ctx.settings.get("pickup_a") or ctx.settings.get("Id_min") or 0.2)

        diff = ctx.electrical.get("diff_87")
        if not isinstance(diff, dict):
            # Bus: sum of feeder currents when provided as i_local / i_remote pair
            diff = differential_operate_restraint(
                i_local=_c(ctx.electrical.get("i_local")),
                i_remote=_c(ctx.electrical.get("i_remote")),
                slope=slope,
                pickup_a=pickup,
            )

        if diff.get("operate_expected") is True:
            fault_hint = True
        elif diff.get("operate_expected") is False and diff.get("status") == "OK":
            fault_hint = False

        result = base_assess("87B", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Bus differential"
        result.metadata["differential"] = diff
        return result


ELEMENT = Element_87B()
