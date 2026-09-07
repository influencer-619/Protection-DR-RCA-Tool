"""Protection element 51 — Time overcurrent with IEC/IEEE inverse curves."""

from __future__ import annotations

from typing import Any, Optional

from protection.curves import inverse_time_s, pickup_multiple, resolve_curve_name
from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


def _num(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class Element_51(ProtectionElement):
    element_code = "51"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("51", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Time overcurrent"

        cfg = ctx.rule_config or {}
        physics = dict(cfg.get("physics") or {})
        curve = resolve_curve_name(
            ctx.settings.get("curve")
            or ctx.settings.get("curve_type")
            or physics.get("default_curve")
        )
        pickup_a = _num(
            ctx.settings.get("pickup_current")
            or ctx.settings.get("pickup")
            or ctx.settings.get("I_pickup")
        )
        tds = _num(
            ctx.settings.get("time_dial")
            or ctx.settings.get("TMS")
            or ctx.settings.get("tds")
        )
        current_a = _num(
            ctx.electrical.get("I_fault_a")
            or ctx.electrical.get("I_max_a")
            or ctx.electrical.get("current_a")
        )

        multiple = pickup_multiple(current_a, pickup_a)
        expected_t = (
            inverse_time_s(multiple=multiple, time_dial=tds or 1.0, curve=curve)
            if multiple is not None and tds is not None
            else None
        )

        timing = dict(result.timing or {})
        timing.update(
            {
                "curve": curve,
                "pickup_current_a": pickup_a,
                "time_dial": tds,
                "current_a": current_a,
                "pickup_multiple": multiple,
                "expected_operate_time_s": expected_t,
                "physics_status": (
                    "CALCULATED"
                    if expected_t is not None
                    else "NOT_CALCULABLE"
                ),
                "physics_reason": (
                    None
                    if expected_t is not None
                    else "Requires validated pickup current, time dial, and measured current"
                ),
            }
        )

        # Compare observed operate time if both available (tolerance from rule)
        obs_t = timing.get("operate_time_s")
        tol = float(physics.get("timing_tolerance_s", 0.05))
        if expected_t is not None and obs_t is not None:
            err = abs(float(obs_t) - expected_t)
            timing["timing_error_s"] = err
            timing["timing_ok"] = err <= tol
            if not timing["timing_ok"] and result.consistency == "CONSISTENT":
                result.consistency = "INCONSISTENT"
                result.metadata["timing_inconsistency"] = True

        # Expected electrical pickup when current exceeds pickup
        if pickup_a is not None and current_a is not None and result.enabled is True:
            if current_a >= pickup_a and result.expected_operation == "UNKNOWN":
                result.expected_operation = "OPERATE"
            elif current_a < pickup_a * 0.95 and result.trip is not True:
                result.expected_operation = "NOT_OPERATE"

        result.timing = timing
        result.metadata["physics"] = {
            "curve": curve,
            "algorithm_version": "1.0.0",
            "method": "IEC_IEEE_inverse_time",
        }
        result.evidence_ids = list(result.evidence_ids) + (
            ["PHYS-51-CURVE"] if expected_t is not None else ["PHYS-51-NOT_CALCULABLE"]
        )
        return result


ELEMENT = Element_51()
