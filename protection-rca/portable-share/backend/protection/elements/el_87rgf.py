"""Protection element 87RGF — Restricted ground fault (operate/restraint on residual)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import (
    _c,
    apply_operate_expect,
    differential_operate_restraint,
    instantaneous_overcurrent,
    measurand_residual_a,
)


class Element_87RGF(ProtectionElement):
    element_code = "87RGF"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        # Prefer differential Id/Ir when both sides present; else residual vs REF pickup.
        fault_hint = False
        slope = float(ctx.settings.get("slope") or ctx.settings.get("k") or 0.3)
        pickup = float(
            ctx.settings.get("pickup_a")
            or ctx.settings.get("Id_min")
            or ctx.settings.get("pickup_current")
            or 0.1
        )

        diff = ctx.electrical.get("diff_87rgf") or ctx.electrical.get("diff_87")
        if not isinstance(diff, dict):
            diff = differential_operate_restraint(
                i_w1=_c(ctx.electrical.get("i_w1") or ctx.electrical.get("i_residual_ct")),
                i_w2=_c(ctx.electrical.get("i_w2") or ctx.electrical.get("i_neutral_ct")),
                slope=slope,
                pickup_a=pickup,
            )

        phys: dict = {"differential": diff}
        if diff.get("operate_expected") is True:
            fault_hint = True
        elif diff.get("operate_expected") is False and diff.get("status") == "OK":
            fault_hint = False
        elif diff.get("status") == "NOT_CALCULABLE":
            # Fallback: residual magnitude vs REF pickup (single-CT REF schemes)
            i0 = measurand_residual_a(ctx.electrical)
            oc = instantaneous_overcurrent(current_a=i0, pickup_a=pickup)
            phys["residual"] = oc
            if oc.get("operate_expected") is True:
                fault_hint = True
            elif oc.get("operate_expected") is False:
                fault_hint = False
            elif ctx.observations.trip is True:
                fault_hint = True

        result = base_assess("87RGF", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Restricted ground fault"
        result.metadata["physics"] = phys
        if isinstance(phys.get("residual"), dict):
            apply_operate_expect(result, phys["residual"])
        elif isinstance(diff, dict) and diff.get("status") == "OK":
            apply_operate_expect(result, diff)
        if (
            diff.get("status") == "NOT_CALCULABLE"
            and not isinstance(phys.get("residual"), dict)
            and ctx.observations.trip is not True
        ):
            result.expected_operation = "UNKNOWN"
            result.consistency = "UNVERIFIABLE"
        return result


ELEMENT = Element_87RGF()
