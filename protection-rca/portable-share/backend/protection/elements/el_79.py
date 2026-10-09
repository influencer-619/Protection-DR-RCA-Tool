"""Protection element 79 — Auto-reclose (shot count / reclaim / success)."""

from __future__ import annotations

from typing import Any, Optional

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


def _reclose_sequence(
    timeline: list,
    *,
    reclaim_s: Optional[float] = None,
    max_shots: Optional[int] = None,
) -> dict[str, Any]:
    """Classify AR shots from timeline reclose / trip / interrupt edges."""
    times: list[float] = []
    trip_after: list[float] = []
    interrupt_after: list[float] = []
    for ev in timeline or []:
        if not isinstance(ev, dict):
            continue
        et = str(ev.get("event_type") or "")
        t = ev.get("t_s")
        if t is None:
            t = ev.get("timestamp")
        try:
            tf = float(t)
        except (TypeError, ValueError):
            continue
        if et == "reclose":
            times.append(tf)
        elif et in ("protection_trip", "breaker_trip_command"):
            trip_after.append(tf)
        elif et == "current_interruption":
            interrupt_after.append(tf)

    shots = len(times)
    if shots == 0 and not (trip_after or interrupt_after):
        return {
            "status": "SCHEME",
            "shots": 0,
            "successful": None,
            "unsuccessful": None,
            "reclaim_ok": None,
            "lockout": None,
            "notes": "No reclose digital / timeline edges — scheme status only",
        }

    # Success heuristic: after last reclose, current interrupts and no further trip
    # within reclaim window (default 30 s when unset).
    reclaim = float(reclaim_s) if reclaim_s and reclaim_s > 0 else 30.0
    successful: Optional[bool] = None
    unsuccessful: Optional[bool] = None
    reclaim_ok: Optional[bool] = None
    lockout: Optional[bool] = None

    if max_shots is not None and max_shots > 0 and shots > max_shots:
        lockout = True
        unsuccessful = True
        successful = False

    if times:
        t_last = max(times)
        cleared = any(ti >= t_last for ti in interrupt_after)
        window_end = t_last + reclaim
        retrip = any(t_last + 0.02 < tt <= window_end for tt in trip_after)
        late_retrip = any(tt > window_end for tt in trip_after)
        if cleared and not retrip and not late_retrip:
            successful = True
            unsuccessful = False
            reclaim_ok = True
        elif retrip or (cleared is False and any(tt > t_last + 0.02 for tt in trip_after)):
            successful = False
            unsuccessful = True
            reclaim_ok = False
        elif cleared and late_retrip:
            # Held through reclaim then faulted again — first reclaim OK
            reclaim_ok = True
            successful = True
            unsuccessful = False

    notes_parts = [f"Autoreclose: {shots} shot(s)"]
    if max_shots:
        notes_parts.append(f"max {max_shots}")
    if lockout:
        notes_parts.append("lockout (shots > max)")
    elif successful:
        notes_parts.append("successful reclaim")
    elif unsuccessful:
        notes_parts.append("unsuccessful — retrip after close")
    if reclaim_s:
        notes_parts.append(f"reclaim={reclaim:.1f}s")

    return {
        "status": "OK" if shots or successful is not None else "INCONCLUSIVE",
        "shots": shots,
        "reclose_times_s": sorted(times),
        "successful": successful,
        "unsuccessful": unsuccessful,
        "reclaim_ok": reclaim_ok,
        "reclaim_s": reclaim if times else None,
        "max_shots": max_shots,
        "lockout": lockout,
        "notes": "; ".join(notes_parts),
    }


class Element_79(ProtectionElement):
    element_code = "79"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        result = base_assess("79", ctx, electrical_fault_hint=False)
        result.metadata["description"] = "Auto-reclose"

        reclaim_s: Optional[float] = None
        for key in ("reclaim_s", "reclaim_ms", "reclaim_time_s"):
            raw = ctx.settings.get(key)
            if raw is None:
                continue
            try:
                v = float(raw)
            except (TypeError, ValueError):
                continue
            reclaim_s = v / 1000.0 if key == "reclaim_ms" and v > 100 else v
            break

        max_shots: Optional[int] = None
        for key in ("max_shots", "shots", "MaxCyc"):
            raw = ctx.settings.get(key)
            if raw is None:
                continue
            try:
                max_shots = int(float(raw))
            except (TypeError, ValueError):
                continue
            break

        seq = _reclose_sequence(ctx.timeline, reclaim_s=reclaim_s, max_shots=max_shots)
        result.metadata["physics"] = {
            "status": seq.get("status") or "SCHEME",
            "operate_expected": None,
            "reclose": seq,
            "notes": seq.get("notes")
            or "79 is autoreclose logic — assess from digital initiate/success only",
        }
        timing = dict(result.timing or {})
        timing["reclose_shots"] = seq.get("shots")
        timing["reclose_successful"] = seq.get("successful")
        timing["reclose_unsuccessful"] = seq.get("unsuccessful")
        timing["reclose_reclaim_ok"] = seq.get("reclaim_ok")
        timing["reclose_lockout"] = seq.get("lockout")
        result.timing = timing
        if result.expected_operation == "OPERATE" and ctx.observations.trip is not True:
            # Pickup/initiate of AR is scheme status, not "operate fault"
            result.expected_operation = "UNKNOWN"
        if seq.get("lockout") is True:
            result.metadata["reclose_outcome"] = "LOCKOUT"
        elif seq.get("unsuccessful") is True:
            result.metadata["reclose_outcome"] = "UNSUCCESSFUL"
        elif seq.get("successful") is True:
            result.metadata["reclose_outcome"] = "SUCCESSFUL"
        return result


ELEMENT = Element_79()
