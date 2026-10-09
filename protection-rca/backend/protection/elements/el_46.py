"""Protection element 46 — Negative-sequence / phase unbalance (I2 ≥ pickup)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import apply_operate_expect, instantaneous_overcurrent


class Element_46(ProtectionElement):
    element_code = "46"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        i2 = ctx.electrical.get("I2") or ctx.electrical.get("i2_mag") or ctx.electrical.get("I2_a")
        try:
            i2_f = float(i2) if i2 is not None else None
        except (TypeError, ValueError):
            i2_f = None
        pickup = (
            ctx.settings.get("pickup_current")
            or ctx.settings.get("pickup")
            or ctx.settings.get("I2_pickup")
        )
        try:
            pickup_f = float(pickup) if pickup is not None else None
        except (TypeError, ValueError):
            pickup_f = None

        phys = instantaneous_overcurrent(current_a=i2_f, pickup_a=pickup_f)
        phys["quantity"] = "I2"
        # Without pickup setting, do not treat any I2>0 as operate-expected
        fault_hint = bool(phys.get("operate_expected") is True)
        if phys.get("status") != "OK" and ctx.observations.trip is True:
            fault_hint = True

        result = base_assess("46", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Negative-sequence / phase unbalance current"
        result.metadata["physics"] = phys
        if i2_f is not None:
            result.metadata["I2"] = i2_f
        apply_operate_expect(result, phys)
        return result


ELEMENT = Element_46()
