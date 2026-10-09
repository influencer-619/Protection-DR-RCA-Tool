"""Protection element 49 — Thermal overload (I²t / heating model)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import apply_operate_expect, measurand_current_a, thermal_i2t


class Element_49(ProtectionElement):
    element_code = "49"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        flc = (
            ctx.settings.get("I_flc")
            or ctx.settings.get("thermal_pickup")
            or ctx.settings.get("pickup_current")
            or ctx.settings.get("pickup")
        )
        try:
            flc_f = float(flc) if flc is not None else None
        except (TypeError, ValueError):
            flc_f = None
        tau = ctx.settings.get("thermal_tau_s") or ctx.settings.get("tau_s")
        try:
            tau_f = float(tau) if tau is not None else None
        except (TypeError, ValueError):
            tau_f = None
        current = measurand_current_a(ctx.electrical)
        # Prefer DR fault-window duration if present
        dur = ctx.electrical.get("fault_duration_s") or ctx.electrical.get("duration_s")
        try:
            dur_f = float(dur) if dur is not None else None
        except (TypeError, ValueError):
            dur_f = None
        fw = (ctx.electrical.get("detectors") or {}).get("fault_window")
        if dur_f is None and isinstance(fw, dict) and fw.get("timestamp_s") is not None:
            # Approximate duration from inception→window if not set
            dur_f = None

        phys = thermal_i2t(
            current_a=current,
            flc_a=flc_f,
            tau_s=tau_f,
            duration_s=dur_f,
        )
        fault_hint = bool(phys.get("operate_expected") is True)
        if phys.get("status") != "OK" and ctx.observations.trip is True:
            fault_hint = True

        result = base_assess("49", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Thermal overload"
        result.metadata["physics"] = phys
        apply_operate_expect(result, phys)
        if phys.get("status") == "OK":
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-49-I2T"]
        return result


ELEMENT = Element_49()
