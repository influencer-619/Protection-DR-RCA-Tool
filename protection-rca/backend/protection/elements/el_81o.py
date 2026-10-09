"""Protection element 81O — Overfrequency (f ≥ pickup)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import (
    apply_operate_expect,
    measurand_frequency_hz,
    threshold_compare,
)


class Element_81O(ProtectionElement):
    element_code = "81O"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        pickup = (
            ctx.settings.get("pickup_hz")
            or ctx.settings.get("pickup_frequency")
            or ctx.settings.get("pickup")
        )
        try:
            pickup_f = float(pickup) if pickup is not None else None
        except (TypeError, ValueError):
            pickup_f = None
        f = measurand_frequency_hz(ctx.electrical)
        phys = threshold_compare(measured=f, pickup=pickup_f, mode="over", unit="Hz")
        fault_hint = bool(phys.get("operate_expected") is True)

        result = base_assess("81O", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Overfrequency"
        result.metadata["physics"] = phys
        apply_operate_expect(result, phys)
        if phys.get("status") == "OK":
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-81O-F"]
        return result


ELEMENT = Element_81O()
