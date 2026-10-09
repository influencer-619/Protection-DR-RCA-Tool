"""Protection element 27 — Undervoltage (V ≤ pickup)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import (
    apply_operate_expect,
    measurand_voltage_v,
    threshold_compare,
)


class Element_27(ProtectionElement):
    element_code = "27"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        # Undervoltage is not "fault indicated" — use V vs pickup only.
        pickup = (
            ctx.settings.get("pickup_voltage")
            or ctx.settings.get("pickup")
            or ctx.settings.get("V_pickup")
        )
        try:
            pickup_f = float(pickup) if pickup is not None else None
        except (TypeError, ValueError):
            pickup_f = None
        v = measurand_voltage_v(ctx.electrical)
        phys = threshold_compare(measured=v, pickup=pickup_f, mode="under", unit="V")
        fault_hint = bool(phys.get("operate_expected") is True)

        result = base_assess("27", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Undervoltage"
        result.metadata["physics"] = phys
        apply_operate_expect(result, phys)
        if phys.get("status") == "OK":
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-27-V"]
        return result


ELEMENT = Element_27()
