"""Protection element 50BF — Breaker failure (timing-aware)."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import breaker_failure_timing


def _timeline_time(timeline: list, event_types: set[str]) -> float | None:
    for ev in timeline:
        if not isinstance(ev, dict):
            continue
        if ev.get("event_type") in event_types:
            t = ev.get("t_s")
            if t is None and ev.get("t_us") is not None:
                try:
                    t = float(ev["t_us"]) / 1e6
                except (TypeError, ValueError):
                    t = None
            if t is not None:
                try:
                    return float(t)
                except (TypeError, ValueError):
                    continue
    return None


class Element_50BF(ProtectionElement):
    element_code = "50BF"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        bf_timer = ctx.settings.get("bf_timer_s") or ctx.settings.get("timer_s")
        try:
            bf_timer_f = float(bf_timer) if bf_timer is not None else None
        except (TypeError, ValueError):
            bf_timer_f = None

        trip_t = ctx.observations.trip_time_s
        if trip_t is None:
            trip_t = _timeline_time(
                ctx.timeline,
                {"protection_trip", "breaker_trip_command"},
            )
        drop_t = _timeline_time(ctx.timeline, {"current_interruption"})
        persists = bool(ctx.electrical.get("current_persists", False))

        timing = ctx.electrical.get("bf_timing")
        if not isinstance(timing, dict):
            timing = breaker_failure_timing(
                trip_time_s=trip_t,
                current_drop_time_s=drop_t,
                bf_timer_s=bf_timer_f,
                current_persists=persists,
            )

        if timing.get("bf_expected") is True:
            fault_hint = True
        elif timing.get("bf_expected") is False:
            fault_hint = False

        result = base_assess("50BF", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "Breaker failure"
        result.metadata["bf_timing"] = timing
        if timing.get("clearing_time_s") is not None:
            if result.timing is None:
                result.timing = {}
            result.timing["clearing_time_s"] = timing["clearing_time_s"]
            result.timing["bf_timer_s"] = timing.get("bf_timer_s")
        return result


ELEMENT = Element_50BF()
