"""Protection element 87T — Transformer differential (operate/restraint aware)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import _c, differential_operate_restraint


class Element_87T(ProtectionElement):
    element_code = "87T"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        slope = float(ctx.settings.get("slope") or ctx.settings.get("k") or 0.3)
        pickup = float(ctx.settings.get("pickup_a") or ctx.settings.get("Id_min") or 0.2)

        diff = ctx.electrical.get("diff_87")
        if not isinstance(diff, dict):
            diff = differential_operate_restraint(
                i_w1=_c(ctx.electrical.get("i_w1")),
                i_w2=_c(ctx.electrical.get("i_w2")),
                slope=slope,
                pickup_a=pickup,
            )

        if diff.get("operate_expected") is True:
            fault_hint = True
        elif diff.get("operate_expected") is False and diff.get("status") == "OK":
            fault_hint = False

        inrush = (ctx.electrical.get("detectors") or {}).get("magnetizing_inrush") or {}
        # Soft restrain: do not force OPERATE expectation during possible inrush
        if inrush.get("status") == "POSSIBLE" and diff.get("operate_expected") is True:
            fault_hint = False

        result = base_assess("87T", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Transformer differential"
        result.metadata["differential"] = diff
        result.metadata["inrush"] = inrush
        return result


ELEMENT = Element_87T()
