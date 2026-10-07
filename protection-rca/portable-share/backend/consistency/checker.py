"""Individual consistency check implementations."""

from __future__ import annotations

from typing import Any, Optional

from app.core.enums import ConsistencyStatus, Severity
from consistency.findings import ConsistencyFinding, new_finding
from protection.models import ProtectionAssessment


SETTING_INVESTIGATION_HINTS = [
    "wrong/stale base setting",
    "different active setting group",
    "setting changed before event",
    "incorrect event-setting association",
    "incorrect channel mapping",
    "relay configuration mismatch",
    "data interpretation problem",
]


def _setting_meta(assessment: ProtectionAssessment) -> tuple[str, str]:
    ref = assessment.setting_reference.get("enabled") or {}
    if isinstance(ref, dict):
        return (
            str(ref.get("source", "NOT AVAILABLE")),
            str(ref.get("version", "NOT AVAILABLE")),
        )
    return ("NOT AVAILABLE", "NOT AVAILABLE")


def check_enabled_vs_pickup(
    assessment: ProtectionAssessment, event_id: str
) -> ConsistencyFinding:
    src, ver = _setting_meta(assessment)
    enabled, pickup = assessment.enabled, assessment.pickup
    if enabled is None or pickup is None:
        return new_finding(
            event_id=event_id,
            element=assessment.element,
            check_type="enabled_vs_pickup",
            setting_source=src,
            setting_version=ver,
            expected="enabled and pickup both known",
            observed=f"enabled={enabled}, pickup={pickup}",
            status=ConsistencyStatus.UNVERIFIABLE.value,
            severity=Severity.MEDIUM.value,
            explanation="Cannot verify enabled vs pickup — data incomplete",
            evidence_ids=assessment.evidence_ids,
            confidence="INCONCLUSIVE",
        )
    if enabled is False and pickup is True:
        return new_finding(
            event_id=event_id,
            element=assessment.element,
            check_type="enabled_vs_pickup",
            setting_source=src,
            setting_version=ver,
            expected="no pickup when element disabled",
            observed=f"enabled=FALSE, pickup=TRUE",
            status=ConsistencyStatus.INCONSISTENT.value,
            severity=Severity.HIGH.value,
            explanation=(
                f"Element {assessment.element} enabled=FALSE but pickup=TRUE. "
                "Do NOT auto-conclude relay malfunction; investigate setting sources."
            ),
            evidence_ids=assessment.evidence_ids,
            confidence="HIGH",
            investigation_hints=SETTING_INVESTIGATION_HINTS,
        )
    return new_finding(
        event_id=event_id,
        element=assessment.element,
        check_type="enabled_vs_pickup",
        setting_source=src,
        setting_version=ver,
        expected="pickup only if enabled",
        observed=f"enabled={enabled}, pickup={pickup}",
        status=ConsistencyStatus.CONSISTENT.value,
        severity=Severity.INFO.value,
        explanation="Enabled vs pickup consistent",
        evidence_ids=assessment.evidence_ids,
        confidence="MEDIUM",
    )


def check_enabled_vs_trip(
    assessment: ProtectionAssessment, event_id: str
) -> ConsistencyFinding:
    src, ver = _setting_meta(assessment)
    enabled, trip = assessment.enabled, assessment.trip
    if enabled is None or trip is None:
        return new_finding(
            event_id=event_id,
            element=assessment.element,
            check_type="enabled_vs_trip",
            setting_source=src,
            setting_version=ver,
            expected="enabled and trip both known",
            observed=f"enabled={enabled}, trip={trip}",
            status=ConsistencyStatus.UNVERIFIABLE.value,
            severity=Severity.MEDIUM.value,
            explanation="Cannot verify enabled vs trip — data incomplete",
            evidence_ids=assessment.evidence_ids,
            confidence="INCONCLUSIVE",
        )
    if enabled is False and trip is True:
        return new_finding(
            event_id=event_id,
            element=assessment.element,
            check_type="enabled_vs_trip",
            setting_source=src,
            setting_version=ver,
            expected="no trip when element disabled",
            observed="enabled=FALSE, trip=TRUE",
            status=ConsistencyStatus.INCONSISTENT.value,
            severity=Severity.CRITICAL.value,
            explanation=(
                f"Element {assessment.element} enabled=FALSE but trip=TRUE. "
                "INCONSISTENT — investigate setting sources; RCA remains INCONCLUSIVE "
                "until active configuration verified. Do NOT auto-conclude relay malfunction."
            ),
            evidence_ids=assessment.evidence_ids,
            confidence="HIGH",
            investigation_hints=SETTING_INVESTIGATION_HINTS,
        )
    return new_finding(
        event_id=event_id,
        element=assessment.element,
        check_type="enabled_vs_trip",
        setting_source=src,
        setting_version=ver,
        expected="trip only if enabled",
        observed=f"enabled={enabled}, trip={trip}",
        status=ConsistencyStatus.CONSISTENT.value,
        severity=Severity.INFO.value,
        explanation="Enabled vs trip consistent",
        evidence_ids=assessment.evidence_ids,
        confidence="MEDIUM",
    )


def check_pickup_vs_trip(
    assessment: ProtectionAssessment, event_id: str
) -> ConsistencyFinding:
    src, ver = _setting_meta(assessment)
    pickup, trip = assessment.pickup, assessment.trip
    if pickup is None or trip is None:
        return new_finding(
            event_id=event_id,
            element=assessment.element,
            check_type="pickup_vs_trip",
            setting_source=src,
            setting_version=ver,
            expected="pickup and trip both known",
            observed=f"pickup={pickup}, trip={trip}",
            status=ConsistencyStatus.UNVERIFIABLE.value,
            severity=Severity.LOW.value,
            explanation="Cannot verify pickup vs trip",
            evidence_ids=assessment.evidence_ids,
            confidence="INCONCLUSIVE",
        )
    if trip is True and pickup is False:
        return new_finding(
            event_id=event_id,
            element=assessment.element,
            check_type="pickup_vs_trip",
            setting_source=src,
            setting_version=ver,
            expected="trip preceded by pickup (unless instantaneous path documented)",
            observed="pickup=FALSE, trip=TRUE",
            status=ConsistencyStatus.INCONSISTENT.value,
            severity=Severity.HIGH.value,
            explanation="Trip without pickup requires investigation",
            evidence_ids=assessment.evidence_ids,
            confidence="MEDIUM",
            investigation_hints=[
                "instantaneous path without separate pickup digital",
                "incorrect channel mapping",
                "missing pickup digital in COMTRADE",
            ],
        )
    return new_finding(
        event_id=event_id,
        element=assessment.element,
        check_type="pickup_vs_trip",
        setting_source=src,
        setting_version=ver,
        expected="trip with prior or concurrent pickup",
        observed=f"pickup={pickup}, trip={trip}",
        status=ConsistencyStatus.CONSISTENT.value,
        severity=Severity.INFO.value,
        explanation="Pickup vs trip consistent",
        evidence_ids=assessment.evidence_ids,
        confidence="MEDIUM",
    )


def check_protection_sequence(
    timeline: list[dict[str, Any]], event_id: str, element: str = "GENERAL"
) -> ConsistencyFinding:
    """Check protection timeline order.

    Strict core: pickup ≤ trip (when both present).
    Clearing cluster (breaker command / 52a / current interrupt) may occur in
    either order — physical interrupt and 52a often swap by tens of ms.

    COMTRADE digitals also jitter by a sample or two: allow ~50 ms slack when
    comparing clearing vs pickup/trip so 52a 6 ms before Start is not HIGH.
    Missing trip (common when only a general trip contact exists) is not itself
    an inconsistency if pickup and clearing are near-simultaneous.
    """
    pickup_key = "protection_pickup"
    trip_key = "protection_trip"
    clearing_keys = frozenset(
        {"breaker_trip_command", "52a_change", "current_interruption"}
    )
    tracked = {pickup_key, trip_key} | clearing_keys
    eps = 1e-6
    # Sample / aux-contact skew tolerance (seconds)
    clear_tol_s = 0.050

    times: dict[str, float] = {}
    for ev in timeline:
        et = str(ev.get("event_type") or "").strip().lower()
        if et in tracked and et not in times:
            try:
                times[et] = float(ev.get("timestamp", 0))
            except (TypeError, ValueError):
                continue

    expected = {
        "order": "Pickup → Trip → Clearing (52a / interrupt, either order)",
        "steps": [
            pickup_key,
            trip_key,
            "breaker_trip_command",
            "52a_change",
            "current_interruption",
        ],
        "note": (
            "52a and current interruption unordered; clearing vs pickup/trip "
            f"allows ±{int(clear_tol_s * 1000)} ms COMTRADE skew"
        ),
    }
    present = [k for k in (pickup_key, trip_key, *sorted(clearing_keys)) if k in times]
    observed = {"times_s": {k: round(times[k], 4) for k in present}}

    if len(present) < 2:
        return new_finding(
            event_id=event_id,
            element=element,
            check_type="protection_sequence",
            setting_source="N/A",
            setting_version="N/A",
            expected=expected,
            observed={**observed, "present": present},
            status=ConsistencyStatus.UNVERIFIABLE.value,
            severity=Severity.LOW.value,
            explanation="Insufficient timeline events for sequence check",
            confidence="INCONCLUSIVE",
        )

    violations: list[str] = []
    notes: list[str] = []
    t_pickup = times.get(pickup_key)
    t_trip = times.get(trip_key)
    clearing_present = {k: times[k] for k in clearing_keys if k in times}
    t_clear0 = min(clearing_present.values()) if clearing_present else None

    if t_pickup is not None and t_trip is not None and t_trip + eps < t_pickup:
        violations.append("trip_before_pickup")

    def _clearing_too_early(ref: float) -> bool:
        assert t_clear0 is not None
        return t_clear0 + clear_tol_s < ref

    if t_trip is not None and t_clear0 is not None and _clearing_too_early(t_trip):
        violations.append("clearing_before_trip")
    elif t_trip is not None and t_clear0 is not None and t_clear0 + eps < t_trip:
        notes.append("clearing_slightly_before_trip_within_tol")

    if t_pickup is not None and t_clear0 is not None and t_trip is None:
        if _clearing_too_early(t_pickup):
            violations.append("clearing_before_pickup")
        elif t_clear0 + eps < t_pickup:
            notes.append("clearing_slightly_before_pickup_within_tol")
        # Trip digital often absent (general trip / orphan) — not a sequence fail
        notes.append("trip_digital_not_observed")

    ok = not violations
    observed["violations"] = violations
    if notes:
        observed["notes"] = notes
    if clearing_present:
        observed["clearing_span_ms"] = round(
            (max(clearing_present.values()) - min(clearing_present.values())) * 1000,
            2,
        )

    if ok and "trip_digital_not_observed" in notes and t_trip is None:
        explanation = (
            "Protection sequence OK within COMTRADE skew; trip contact not in "
            "timeline (general/orphan trip common) — pickup and clearing observed"
        )
    elif ok:
        explanation = (
            "Protection sequence order check (pickup→trip→clearing; "
            "52a/interrupt unordered; ±50 ms clearing skew allowed)"
        )
    else:
        explanation = f"Protection sequence violated: {', '.join(violations)}"

    return new_finding(
        event_id=event_id,
        element=element,
        check_type="protection_sequence",
        setting_source="N/A",
        setting_version="N/A",
        expected=expected,
        observed=observed,
        status=(
            ConsistencyStatus.CONSISTENT.value
            if ok
            else ConsistencyStatus.INCONSISTENT.value
        ),
        severity=Severity.MEDIUM.value if ok else Severity.HIGH.value,
        explanation=explanation,
        confidence="MEDIUM",
    )


def check_element_family(
    assessments: list[ProtectionAssessment],
    event_id: str,
    check_type: str,
    elements: list[str],
) -> ConsistencyFinding:
    subset = [a for a in assessments if a.element in elements]
    if not subset:
        return new_finding(
            event_id=event_id,
            element=",".join(elements),
            check_type=check_type,
            setting_source="NOT AVAILABLE",
            setting_version="NOT AVAILABLE",
            expected=f"data for {elements}",
            observed="no assessments",
            status=ConsistencyStatus.UNVERIFIABLE.value,
            severity=Severity.LOW.value,
            explanation=f"{check_type}: no element assessments available",
            confidence="INCONCLUSIVE",
        )
    inconsistent = [a for a in subset if a.consistency == "INCONSISTENT"]
    if inconsistent:
        return new_finding(
            event_id=event_id,
            element=",".join(a.element for a in inconsistent),
            check_type=check_type,
            setting_source="MIXED",
            setting_version="MIXED",
            expected="consistent operation vs settings",
            observed="INCONSISTENT elements present",
            status=ConsistencyStatus.INCONSISTENT.value,
            severity=Severity.HIGH.value,
            explanation=f"{check_type} family has inconsistent elements",
            confidence="MEDIUM",
            investigation_hints=SETTING_INVESTIGATION_HINTS,
        )
    unverifiable = [a for a in subset if a.consistency == "UNVERIFIABLE"]
    if len(unverifiable) == len(subset):
        return new_finding(
            event_id=event_id,
            element=",".join(elements),
            check_type=check_type,
            setting_source="NOT AVAILABLE",
            setting_version="NOT AVAILABLE",
            expected="verifiable assessments",
            observed="all UNVERIFIABLE",
            status=ConsistencyStatus.UNVERIFIABLE.value,
            severity=Severity.MEDIUM.value,
            explanation=f"{check_type}: unverifiable",
            confidence="INCONCLUSIVE",
        )
    return new_finding(
        event_id=event_id,
        element=",".join(a.element for a in subset),
        check_type=check_type,
        setting_source="MIXED",
        setting_version="MIXED",
        expected="family consistent",
        observed="no critical inconsistencies",
        status=ConsistencyStatus.CONSISTENT.value,
        severity=Severity.INFO.value,
        explanation=f"{check_type} family check passed",
        confidence="MEDIUM",
    )
