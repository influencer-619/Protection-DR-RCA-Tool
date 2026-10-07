"""IEEE/PSRC-style DFR event classifier.

Industry order (PSRC disturbance recording / DFR practice):
  1) Validate record
  2) Classify event: FAULT vs non-fault (energization / motor / switching / disturbance)
  3) Only then publish shunt fault type (AG/AB/…) and fault-side RCA

Hard FAULT gate uses: voltage sag + trip + duration + harmonics (H2)
before AG/AB typing / feeder RCA.

References (methods, not verbatim text):
  - IEEE PES-PSRC “Considerations for Use of Disturbance Recorders”
  - ERLPhase / GaTech DFR event-analysis practice (pre-fault, V/I, SOE, harmonics)
  - SEL event-report analysis (voltage collapse + sequence for type)
  - CIGRE / industry inrush discrimination (H2, no trip)
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from electrical_analysis.analyzer import ElectricalAnalysisResult

# Duration bands (ms) — cycle-aware defaults at 50 Hz (1 cyc ≈ 20 ms)
# SHORT: < ~2 cycles (switching spike / noise)
# TYPICAL: cleared shunt fault / zone operate window
# LONG: sustained (motor start, uncleared OC, charging tail) — not FAULT-confirmed alone
_DURATION_SHORT_MS = 40.0
_DURATION_TYPICAL_MAX_MS = 500.0
_DURATION_FAULT_MAX_MS = 2000.0  # delayed OC still plausible as fault clearance


class EventClass:
    FAULT = "FAULT"
    ENERGIZATION = "ENERGIZATION"  # transformer magnetizing inrush / charging
    MOTOR_START = "MOTOR_START"
    SWITCHING = "SWITCHING"  # controlled close / station-tie / reclose
    DISTURBANCE = "DISTURBANCE"  # abnormal I/V but not confirmed shunt fault
    UNKNOWN = "UNKNOWN"


class DurationBand:
    SHORT = "SHORT"
    TYPICAL = "TYPICAL"
    LONG = "LONG"
    UNKNOWN = "UNKNOWN"


@dataclass
class EventClassificationResult:
    event_class: str
    status: str  # CONFIRMED | PROBABLE | POSSIBLE | INCONCLUSIVE
    confidence: str  # HIGH | MEDIUM | LOW | INCONCLUSIVE
    evidence: dict[str, Any] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def is_fault(self) -> bool:
        return self.event_class == EventClass.FAULT


def _tl_type(ev: Any) -> str:
    if isinstance(ev, dict):
        return str(ev.get("event_type") or "").lower()
    return str(getattr(ev, "event_type", "") or "").lower()


def _tl_meta(ev: Any) -> dict[str, Any]:
    if isinstance(ev, dict):
        m = ev.get("metadata") or ev.get("payload") or {}
        if isinstance(m, str):
            return {}
        return m if isinstance(m, dict) else {}
    m = getattr(ev, "metadata", None)
    return m if isinstance(m, dict) else {}


def _rms_ok(elec: ElectricalAnalysisResult, roles: set[str]) -> dict[str, float]:
    out: dict[str, float] = {}
    for ch, role in (elec.channel_roles or {}).items():
        r = str(role or "").upper().strip()
        if r not in roles:
            continue
        sr = (elec.rms or {}).get(ch)
        if sr is None or getattr(sr, "status", None) != "OK":
            continue
        try:
            out[r] = float(sr.value)
        except (TypeError, ValueError):
            continue
    return out


def _tl_timestamp(ev: Any) -> Optional[float]:
    if isinstance(ev, dict):
        for key in ("timestamp", "t_s", "time_s"):
            if ev.get(key) is not None:
                try:
                    return float(ev[key])
                except (TypeError, ValueError):
                    continue
        t_us = ev.get("t_us")
        if t_us is not None:
            try:
                return float(t_us) / 1_000_000.0
            except (TypeError, ValueError):
                return None
        return None
    ts = getattr(ev, "timestamp", None)
    if ts is not None:
        try:
            return float(ts)
        except (TypeError, ValueError):
            return None
    return None


def _duration_band(duration_ms: Optional[float]) -> str:
    if duration_ms is None:
        return DurationBand.UNKNOWN
    if duration_ms < _DURATION_SHORT_MS:
        return DurationBand.SHORT
    if duration_ms <= _DURATION_TYPICAL_MAX_MS:
        return DurationBand.TYPICAL
    return DurationBand.LONG


def _duration_from_timeline(timeline: list[Any]) -> dict[str, Any]:
    """Inception → clearance (or trip) duration for the DFR fault gate."""
    t_inception: Optional[float] = None
    t_current_up: Optional[float] = None
    t_v_change: Optional[float] = None
    t_trip: Optional[float] = None
    t_interrupt: Optional[float] = None

    for e in timeline:
        et = _tl_type(e)
        ts = _tl_timestamp(e)
        if ts is None:
            continue
        if et == "fault_inception":
            t_inception = ts if t_inception is None else min(t_inception, ts)
        elif et == "current_increase":
            t_current_up = ts if t_current_up is None else min(t_current_up, ts)
        elif et == "voltage_change":
            t_v_change = ts if t_v_change is None else min(t_v_change, ts)
        elif et in ("protection_trip", "breaker_trip_command"):
            t_trip = ts if t_trip is None else min(t_trip, ts)
        elif et == "current_interruption":
            t_interrupt = ts if t_interrupt is None else min(t_interrupt, ts)

    starts = [t for t in (t_inception, t_current_up, t_v_change) if t is not None]
    t0 = min(starts) if starts else None

    duration_ms: Optional[float] = None
    duration_method: Optional[str] = None
    cleared = t_interrupt is not None
    if t0 is not None and t_interrupt is not None and t_interrupt >= t0:
        duration_ms = round((t_interrupt - t0) * 1000.0, 1)
        duration_method = "inception_to_interrupt"
    elif t0 is not None and t_trip is not None and t_trip >= t0:
        # Weaker: operate time only (clearance not seen in DR window)
        duration_ms = round((t_trip - t0) * 1000.0, 1)
        duration_method = "inception_to_trip"

    band = _duration_band(duration_ms)
    # Plausible cleared-fault window for CONFIRMED (allow delayed OC up to 2 s)
    fault_duration_ok = bool(
        cleared
        and duration_ms is not None
        and _DURATION_SHORT_MS <= duration_ms <= _DURATION_FAULT_MAX_MS
    )
    # Measured operate/clear span long and still uncleared → sustained event
    sustained_uncleared = bool(
        (not cleared)
        and duration_ms is not None
        and duration_ms > _DURATION_TYPICAL_MAX_MS
    )

    return {
        "duration_ms": duration_ms,
        "duration_band": band,
        "duration_method": duration_method,
        "cleared": cleared,
        "fault_duration_ok": fault_duration_ok,
        "sustained_uncleared": sustained_uncleared,
        "t0_s": t0,
        "t_trip_s": t_trip,
        "t_interrupt_s": t_interrupt,
    }


def _collect_flags(
    elec: ElectricalAnalysisResult,
    *,
    timeline: Optional[list[Any]] = None,
    assessments: Optional[list[Any]] = None,
    digital_channel_names: Optional[list[str]] = None,
) -> dict[str, Any]:
    tl = list(timeline or [])
    types = {_tl_type(e) for e in tl}

    current_increase = "current_increase" in types or "fault_inception" in types
    voltage_sag = False
    strong_voltage_sag = False
    for e in tl:
        if _tl_type(e) != "voltage_change":
            continue
        meta = _tl_meta(e)
        # Timeline stores drop when env < baseline * 0.85
        base = meta.get("baseline_rms")
        val = meta.get("value_rms")
        try:
            if base is not None and val is not None and float(base) > 1e-9:
                ratio = float(val) / float(base)
                if ratio < 0.85:
                    voltage_sag = True
                if ratio < 0.70:
                    strong_voltage_sag = True
        except (TypeError, ValueError):
            voltage_sag = True

    # Fallback: if V channels exist and are very low vs typical secondary — weak only
    v_rms = _rms_ok(elec, {"VA", "VB", "VC", "V"})
    i_rms = _rms_ok(elec, {"IA", "IB", "IC", "I"})

    from protection.operate_evidence import (
        assessment_has_operate_evidence,
        is_assertable_timeline_event,
    )

    protection_trip = False
    protection_pickup = False
    for a in assessments or []:
        d = a.to_dict() if hasattr(a, "to_dict") else (a if isinstance(a, dict) else {})
        if not assessment_has_operate_evidence(d):
            continue
        act = str(d.get("actual_operation") or "").upper()
        # Trip only from explicit trip assert — not pickup framed as OPERATED
        if d.get("trip") is True or act == "TRIPPED":
            protection_trip = True
        elif act == "OPERATED" and d.get("trip") is not False and d.get("pickup") is not True:
            protection_trip = True
        if d.get("pickup") is True or act in ("PICKED_UP", "OPERATED", "TRIPPED"):
            protection_pickup = True

    # Timeline: COMTRADE digital or clear relay SER / event report (not station SOE)
    for e in tl:
        if not is_assertable_timeline_event(e):
            continue
        et = _tl_type(e)
        if et in ("protection_trip", "breaker_trip_command"):
            protection_trip = True
        if et == "protection_pickup":
            protection_pickup = True

    breaker_change = any(t in types for t in ("52a_change", "52b_change"))
    current_interrupt = "current_interruption" in types

    det = getattr(elec, "detectors", None) or {}
    inrush = det.get("magnetizing_inrush") if isinstance(det, dict) else None
    inrush_possible = isinstance(inrush, dict) and str(
        inrush.get("status") or ""
    ).upper() == "POSSIBLE"

    names = [str(n) for n in (digital_channel_names or []) if n]
    # Asserted digital names from timeline sources
    for e in tl:
        src = ""
        if isinstance(e, dict):
            src = str(e.get("source") or "")
        else:
            src = str(getattr(e, "source", "") or "")
        if src.lower().startswith("digital:"):
            names.append(src.split(":", 1)[-1])

    # Lazy import — avoid circular import with fault_analysis.__init__
    from fault_analysis import motor_start_context

    motor = motor_start_context(
        names,
        detectors=det if isinstance(det, dict) else {},
        assessments=assessments,
    )

    name_blob = " ".join(names).upper()
    switching_name = bool(
        re_search_switching(name_blob)
        or any(
            x in name_blob
            for x in (
                "ANY START",
                "STN_UNIT_TIE",
                "STATION_TIE",
                "UNIT_STN_TIE",
                "CHECKSYNC",
                "SYNCH PERMIT",
            )
        )
    )
    # Switching: breaker status change / close without fault trip + no strong V sag
    switching_sig = bool(
        (breaker_change or switching_name)
        and not protection_trip
        and not strong_voltage_sag
    )

    dur = _duration_from_timeline(tl)

    return {
        "current_increase": current_increase,
        "voltage_sag": voltage_sag,
        "strong_voltage_sag": strong_voltage_sag,
        "protection_trip": protection_trip,
        "protection_pickup": protection_pickup,
        "breaker_change": breaker_change,
        "current_interrupt": current_interrupt,
        "inrush_possible": inrush_possible,
        "motor": motor,
        "switching_signature": switching_sig,
        "has_voltage_channels": bool(v_rms),
        "has_current_channels": bool(i_rms),
        "v_rms": v_rms,
        "i_rms": i_rms,
        "timeline_types": sorted(types),
        **dur,
    }


def re_search_switching(blob: str) -> bool:
    import re

    return bool(
        re.search(
            r"\bTIE\b|STATION.?TIE|UNIT.?STN|CLOSE|CB\s*CLOSE|52A|CHECK.?SYNC",
            blob,
            re.I,
        )
    )


def classify_dfr_event(
    elec: ElectricalAnalysisResult,
    *,
    timeline: Optional[list[Any]] = None,
    assessments: Optional[list[Any]] = None,
    digital_channel_names: Optional[list[str]] = None,
) -> EventClassificationResult:
    """Classify DR event class before shunt fault typing / fault-side RCA."""
    flags = _collect_flags(
        elec,
        timeline=timeline,
        assessments=assessments,
        digital_channel_names=digital_channel_names,
    )
    reasons: list[str] = []
    limitations: list[str] = []

    inrush = flags["inrush_possible"]
    motor = flags["motor"] if isinstance(flags["motor"], dict) else {}
    trip = flags["protection_trip"]
    v_sag = flags["voltage_sag"]
    v_strong = flags["strong_voltage_sag"]
    i_up = flags["current_increase"]
    switching = flags["switching_signature"]
    dur_ms = flags.get("duration_ms")
    dur_band = str(flags.get("duration_band") or DurationBand.UNKNOWN)
    cleared = bool(flags.get("cleared"))
    fault_dur_ok = bool(flags.get("fault_duration_ok"))

    def _dur_note() -> None:
        if dur_ms is not None:
            reasons.append(
                f"Duration {dur_ms:g} ms ({dur_band}"
                + ("; cleared" if cleared else "; not cleared in DR")
                + ")"
            )
        elif i_up or trip or v_sag:
            limitations.append(
                "Event duration NOT AVAILABLE — inception/clearance timestamps missing"
            )

    # --- Non-fault signatures first (PSRC/DFR practice) ---
    if inrush and not trip and not v_strong:
        reasons.append("Magnetizing inrush POSSIBLE (elevated H2)")
        if not v_sag:
            reasons.append("No strong phase-voltage collapse")
        if flags["protection_pickup"] and not trip:
            reasons.append("Protection pickup without trip (restrained energization pattern)")
        if dur_band == DurationBand.LONG or (not cleared and dur_band != DurationBand.TYPICAL):
            reasons.append("Duration / uncleared profile consistent with energization, not shunt fault")
        _dur_note()
        return EventClassificationResult(
            event_class=EventClass.ENERGIZATION,
            status="PROBABLE",
            confidence="MEDIUM",
            evidence=flags,
            reasons=reasons,
            limitations=[
                "DFR class ENERGIZATION — do not publish shunt fault type (AG/AB/…) "
                "from phase-current imbalance alone"
            ],
        )

    # Motor start: do not require absence of V sag — starting current often pulls voltage.
    # Only a trip digital displaces this class toward FAULT.
    if motor.get("likely") and not trip:
        reasons.append("Motor-protection / starting-current signature")
        if motor.get("pickup_without_trip"):
            reasons.append("OC/46 pickup without trip digital")
        if v_strong:
            reasons.append(
                "Voltage sag present but no trip — consistent with motor starting current, "
                "not a cleared shunt fault"
            )
        if dur_band == DurationBand.LONG or not cleared:
            reasons.append("Sustained / uncleared current supports motor start, not feeder fault")
        _dur_note()
        return EventClassificationResult(
            event_class=EventClass.MOTOR_START,
            status="PROBABLE",
            confidence="MEDIUM",
            evidence=flags,
            reasons=reasons,
            limitations=[
                "DFR class MOTOR_START — motor start starting current is not a feeder shunt fault"
            ],
        )

    if switching and not trip and not v_strong and (i_up or flags["breaker_change"]):
        reasons.append("Switching / breaker-status signature without fault trip")
        if not v_sag:
            reasons.append("No strong phase-voltage collapse")
        if dur_band == DurationBand.SHORT:
            reasons.append("Short duration consistent with switching transient")
        _dur_note()
        return EventClassificationResult(
            event_class=EventClass.SWITCHING,
            status="PROBABLE" if flags["breaker_change"] else "POSSIBLE",
            confidence="MEDIUM" if flags["breaker_change"] else "LOW",
            evidence=flags,
            reasons=reasons,
            limitations=[
                "DFR class SWITCHING — controlled switching / tie close is not a shunt fault"
            ],
        )

    # Sustained current, no V collapse, no trip → not a cleared shunt fault
    if (
        i_up
        and not v_sag
        and not trip
        and (dur_band == DurationBand.LONG or (not cleared and dur_ms is not None and dur_ms > _DURATION_TYPICAL_MAX_MS))
    ):
        reasons.append("Sustained current without voltage collapse or trip")
        _dur_note()
        return EventClassificationResult(
            event_class=EventClass.DISTURBANCE,
            status="POSSIBLE",
            confidence="LOW",
            evidence=flags,
            reasons=reasons,
            limitations=[
                "DFR class DISTURBANCE — long/uncleared current; shunt fault type suppressed"
            ],
        )

    # --- Fault gate: V + I + trip + duration (SEL/DFR practice) ---
    if v_strong and i_up:
        reasons.append("Strong phase-voltage sag with current increase")
        if trip:
            reasons.append("Protection trip asserted")
            _dur_note()
            if fault_dur_ok:
                reasons.append("Clearance duration in plausible fault window")
                return EventClassificationResult(
                    event_class=EventClass.FAULT,
                    status="CONFIRMED",
                    confidence="HIGH",
                    evidence=flags,
                    reasons=reasons,
                )
            if cleared and dur_band == DurationBand.SHORT:
                limitations.append(
                    "Cleared duration shorter than ~2 cycles — verify not a switching spike"
                )
            elif not cleared:
                limitations.append(
                    "Current interruption NOT OBSERVED — fault class not CONFIRMED on duration"
                )
            else:
                limitations.append(
                    "Duration outside typical cleared-fault window — fault class PROBABLE"
                )
            return EventClassificationResult(
                event_class=EventClass.FAULT,
                status="PROBABLE",
                confidence="MEDIUM",
                evidence=flags,
                reasons=reasons,
                limitations=limitations,
            )
        reasons.append("No trip digital — fault class PROBABLE pending trip/clearance evidence")
        _dur_note()
        return EventClassificationResult(
            event_class=EventClass.FAULT,
            status="PROBABLE",
            confidence="MEDIUM",
            evidence=flags,
            reasons=reasons,
            limitations=limitations
            or ["Trip/clearance duration incomplete — FAULT not CONFIRMED"],
        )

    if v_sag and i_up and trip:
        reasons.append("Voltage sag + current increase + protection trip")
        _dur_note()
        status = "CONFIRMED" if fault_dur_ok else "PROBABLE"
        conf = "HIGH" if fault_dur_ok else "MEDIUM"
        if fault_dur_ok:
            reasons.append("Clearance duration in plausible fault window")
        elif not cleared:
            limitations.append("Clearance duration incomplete — FAULT not CONFIRMED")
        return EventClassificationResult(
            event_class=EventClass.FAULT,
            status=status,
            confidence=conf,
            evidence=flags,
            reasons=reasons,
            limitations=limitations,
        )

    # Trip + I without V: FAULT only if duration looks like clearance, else disturbance
    if trip and i_up:
        reasons.append("Protection trip with current increase")
        _dur_note()
        if not flags["has_voltage_channels"]:
            limitations.append("Voltage channels NOT AVAILABLE — fault class not CONFIRMED")
        elif not v_sag:
            limitations.append("No voltage sag detected — verify CT/VT mapping and fault window")
        if dur_band == DurationBand.LONG and not cleared and not v_sag:
            limitations.append(
                "Long uncleared duration without voltage sag — treating as DISTURBANCE"
            )
            return EventClassificationResult(
                event_class=EventClass.DISTURBANCE,
                status="POSSIBLE",
                confidence="LOW",
                evidence=flags,
                reasons=reasons,
                limitations=limitations,
            )
        return EventClassificationResult(
            event_class=EventClass.FAULT,
            status="PROBABLE",
            confidence="LOW" if not v_sag else "MEDIUM",
            evidence=flags,
            reasons=reasons,
            limitations=limitations,
        )

    # Current-only abnormality without V collapse / trip → disturbance, not shunt fault
    if i_up and not v_sag and not trip:
        reasons.append("Current increase without voltage collapse or trip")
        _dur_note()
        limitations.append(
            "DFR class DISTURBANCE — current-only signature; shunt fault type suppressed"
        )
        return EventClassificationResult(
            event_class=EventClass.DISTURBANCE,
            status="POSSIBLE",
            confidence="LOW",
            evidence=flags,
            reasons=reasons,
            limitations=limitations,
        )

    if not flags["has_current_channels"]:
        limitations.append("Phase current channels NOT AVAILABLE for DFR classification")
    return EventClassificationResult(
        event_class=EventClass.UNKNOWN,
        status="INCONCLUSIVE",
        confidence="INCONCLUSIVE",
        evidence=flags,
        reasons=["Insufficient V/I/digital evidence for DFR event class"],
        limitations=limitations
        or ["DFR event class UNKNOWN — engineer review required"],
    )
