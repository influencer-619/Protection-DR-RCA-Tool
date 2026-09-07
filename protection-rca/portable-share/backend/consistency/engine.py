"""Consistency checker engine — runs before RCA."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any

from consistency.checker import (
    check_element_family,
    check_enabled_vs_pickup,
    check_enabled_vs_trip,
    check_pickup_vs_trip,
    check_protection_sequence,
)
from consistency.findings import ConsistencyFinding
from protection.models import ProtectionAssessment


@dataclass
class ConsistencyResult:
    findings: list[ConsistencyFinding] = field(default_factory=list)
    has_critical_setting_inconsistency: bool = False
    rca_must_remain_inconclusive: bool = False
    summary_status: str = "UNVERIFIABLE"

    def to_dict(self) -> dict[str, Any]:
        return {
            "findings": [f.to_dict() for f in self.findings],
            "has_critical_setting_inconsistency": self.has_critical_setting_inconsistency,
            "rca_must_remain_inconclusive": self.rca_must_remain_inconclusive,
            "summary_status": self.summary_status,
        }


def summarize_consistency_statuses(statuses: set[str]) -> str:
    """Overall lamp: INCONSISTENT wins; else CONSISTENT if any pass (UNVERIFIABLE does not force yellow)."""
    if "INCONSISTENT" in statuses:
        return "INCONSISTENT"
    if "CONSISTENT" in statuses:
        return "CONSISTENT"
    if "DATA_QUALITY_ISSUE" in statuses:
        return "DATA_QUALITY_ISSUE"
    if "UNVERIFIABLE" in statuses:
        return "UNVERIFIABLE"
    return "NOT_AVAILABLE"


class ConsistencyEngine:
    """Compare observed behavior vs expected vs applicable settings."""

    def run(
        self,
        *,
        event_id: str,
        assessments: list[ProtectionAssessment],
        timeline: list[dict[str, Any]] | None = None,
    ) -> ConsistencyResult:
        timeline = timeline or []
        findings: list[ConsistencyFinding] = []

        for a in assessments:
            # No evidence at all — skip (do not emit catalog noise)
            if a.enabled is None and a.pickup is None and a.trip is None:
                continue
            # Need a digital observation side to judge
            if a.pickup is None and a.trip is None:
                continue
            # Need settings (enabled) to judge consistency vs settings
            if a.enabled is None:
                continue
            findings.append(check_enabled_vs_pickup(a, event_id))
            findings.append(check_enabled_vs_trip(a, event_id))
            findings.append(check_pickup_vs_trip(a, event_id))

        seq = check_protection_sequence(timeline, event_id)
        # Only keep sequence when it is actionable (CONSISTENT / INCONSISTENT)
        if seq.status != "UNVERIFIABLE":
            findings.append(seq)

        families = [
            ("distance", ["21", "21G", "21P"]),
            ("directional", ["67", "67N", "67P"]),
            ("earth_fault", ["50N", "51N", "67N", "87RGF"]),
            ("overcurrent", ["50", "51", "50P", "51P"]),
            ("voltage", ["27", "59"]),
            ("frequency", ["81U", "81O", "81R"]),
            ("differential", ["87T", "87L", "87B", "87G", "87RGF"]),
            ("power", ["32R"]),
            ("unbalance", ["46"]),
            ("power_swing", ["68"]),
            ("out_of_step", ["78"]),
            ("breaker_failure", ["50BF"]),
            ("auto_reclose", ["79"]),
            ("lockout", ["86"]),
            ("synchronism", ["25"]),
        ]
        for check_type, elements in families:
            if not any(a.element in elements for a in assessments):
                continue
            finding = check_element_family(assessments, event_id, check_type, elements)
            if finding.status == "UNVERIFIABLE":
                continue
            findings.append(finding)

        critical = False
        for f in findings:
            if (
                f.status == "INCONSISTENT"
                and f.check_type in ("enabled_vs_pickup", "enabled_vs_trip")
                and "enabled=FALSE" in f.observed
            ):
                critical = True
                break

        statuses = {f.status for f in findings}
        summary = summarize_consistency_statuses(statuses)

        return ConsistencyResult(
            findings=findings,
            has_critical_setting_inconsistency=critical,
            rca_must_remain_inconclusive=critical,
            summary_status=summary,
        )
