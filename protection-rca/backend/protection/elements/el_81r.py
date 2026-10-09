"""Protection element 81R — ROCOF (df/dt ≥ pickup)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import apply_operate_expect, threshold_compare


class Element_81R(ProtectionElement):
    element_code = "81R"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        pickup = (
            ctx.settings.get("pickup_rocof")
            or ctx.settings.get("pickup_hz_s")
            or ctx.settings.get("pickup")
        )
        try:
            pickup_f = float(pickup) if pickup is not None else None
        except (TypeError, ValueError):
            pickup_f = None
        rocof = ctx.electrical.get("rocof_hz_s") or ctx.electrical.get("df_dt")
        try:
            rocof_f = abs(float(rocof)) if rocof is not None else None
        except (TypeError, ValueError):
            rocof_f = None
        phys = threshold_compare(
            measured=rocof_f, pickup=pickup_f, mode="over", unit="Hz/s"
        )
        fault_hint = bool(phys.get("operate_expected") is True)

        result = base_assess("81R", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Rate of change of frequency (ROCOF)"
        result.metadata["physics"] = phys
        apply_operate_expect(result, phys)
        if phys.get("status") == "OK":
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-81R-ROCOF"]
        return result


ELEMENT = Element_81R()
