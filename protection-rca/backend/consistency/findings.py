"""Consistency finding model."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional
import uuid

from app.core.enums import ConsistencyStatus, Severity


@dataclass
class ConsistencyFinding:
    finding_id: str
    event_id: str
    element: str
    check_type: str
    setting_source: str
    setting_version: str
    expected: str
    observed: str
    status: str  # CONSISTENT | INCONSISTENT | UNVERIFIABLE | DATA_QUALITY_ISSUE
    severity: str
    evidence_ids: list[str] = field(default_factory=list)
    explanation: str = ""
    confidence: str = "INCONCLUSIVE"
    investigation_hints: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def new_finding(
    *,
    event_id: str,
    element: str,
    check_type: str,
    setting_source: str,
    setting_version: str,
    expected: str,
    observed: str,
    status: str,
    severity: str,
    explanation: str,
    evidence_ids: Optional[list[str]] = None,
    confidence: str = "MEDIUM",
    investigation_hints: Optional[list[str]] = None,
) -> ConsistencyFinding:
    return ConsistencyFinding(
        finding_id=f"cf-{uuid.uuid4().hex[:12]}",
        event_id=event_id,
        element=element,
        check_type=check_type,
        setting_source=setting_source,
        setting_version=setting_version,
        expected=expected,
        observed=observed,
        status=status,
        severity=severity,
        evidence_ids=list(evidence_ids or []),
        explanation=explanation,
        confidence=confidence,
        investigation_hints=list(investigation_hints or []),
    )


# Re-export enums used by checkers
__all__ = [
    "ConsistencyFinding",
    "ConsistencyStatus",
    "Severity",
    "new_finding",
]
