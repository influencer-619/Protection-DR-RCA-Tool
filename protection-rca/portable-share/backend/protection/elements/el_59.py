"""Protection element 59 — Overvoltage (V ≥ pickup)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import (
    apply_operate_expect,
    measurand_voltage_max_v,
    threshold_compare,
)


class Element_59(ProtectionElement):
    element_code = "59"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        pickup = (
            ctx.settings.get("pickup_voltage")
            or ctx.settings.get("pickup")
            or ctx.settings.get("V_pickup")
        )
        try:
            pickup_f = float(pickup) if pickup is not None else None
        except (TypeError, ValueError):
            pickup_f = None
        v = measurand_voltage_max_v(ctx.electrical)
        phys = threshold_compare(measured=v, pickup=pickup_f, mode="over", unit="V")
        fault_hint = bool(phys.get("operate_expected") is True)

        result = base_assess("59", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Overvoltage"
        result.metadata["physics"] = phys
        apply_operate_expect(result, phys)
        if phys.get("status") == "OK":
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-59-V"]
        return result


ELEMENT = Element_59()
