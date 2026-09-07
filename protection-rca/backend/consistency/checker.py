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
    order = [
        "protection_pickup",
        "protection_trip",
        "breaker_trip_command",
        "52a_change",
        "current_interruption",
    ]
    times: dict[str, float] = {}
    for ev in timeline:
        et = ev.get("event_type")
        if et in order and et not in times:
            times[et] = float(ev.get("timestamp", 0))
    present = [e for e in order if e in times]
    if len(present) < 2:
        return new_finding(
            event_id=event_id,
            element=element,
            check_type="protection_sequence",
            setting_source="N/A",
            setting_version="N/A",
            expected="Pickup → Trip → Breaker → Current interruption",
            observed=f"events present: {present}",
            status=ConsistencyStatus.UNVERIFIABLE.value,
            severity=Severity.LOW.value,
            explanation="Insufficient timeline events for sequence check",
            confidence="INCONCLUSIVE",
        )
    ok = all(
        times[present[i]] <= times[present[i + 1]] + 1e-9
        for i in range(len(present) - 1)
    )
    return new_finding(
        event_id=event_id,
        element=element,
        check_type="protection_sequence",
        setting_source="N/A",
        setting_version="N/A",
        expected="monotonic Pickup → Trip → Breaker → Interruption",
        observed=str({k: times[k] for k in present}),
        status=(
            ConsistencyStatus.CONSISTENT.value
            if ok
            else ConsistencyStatus.INCONSISTENT.value
        ),
        severity=Severity.MEDIUM.value if ok else Severity.HIGH.value,
        explanation="Protection sequence order check",
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
