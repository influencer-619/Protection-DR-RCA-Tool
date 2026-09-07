"""Final decision engine — never forces a conclusion."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from app.core.enums import DecisionState, ConfidenceLevel
from consistency.engine import ConsistencyResult
from rca import RCAResult


@dataclass
class DecisionResult:
    state: str
    confidence: str
    reasons: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    requires_engineer_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DecisionEngine:
    def decide(
        self,
        *,
        unsupported_format: bool = False,
        data_insufficient: bool = False,
        consistency: Optional[ConsistencyResult] = None,
        rca: Optional[RCAResult] = None,
        warnings: Optional[list[str]] = None,
    ) -> DecisionResult:
        warnings = warnings or []
        reasons: list[str] = []
        actions: list[str] = []

        if unsupported_format:
            return DecisionResult(
                state=DecisionState.UNSUPPORTED_FORMAT.value,
                confidence=ConfidenceLevel.INCONCLUSIVE.value,
                reasons=["COMTRADE/format unsupported or unvalidated"],
                recommended_actions=["Provide supported COMTRADE CFG/DAT or CFF"],
                requires_engineer_review=True,
            )

        if data_insufficient:
            return DecisionResult(
                state=DecisionState.DATA_INSUFFICIENT.value,
                confidence=ConfidenceLevel.INCONCLUSIVE.value,
                reasons=["Insufficient disturbance record data for analysis"],
                recommended_actions=["Upload complete CFG+DAT/CFF and settings"],
                requires_engineer_review=True,
            )

        if consistency and consistency.rca_must_remain_inconclusive:
            reasons.append(
                "Critical setting inconsistency — RCA INCONCLUSIVE until settings verified"
            )
            actions.extend(
                [
                    "Verify event-specific / active setting group",
                    "Confirm setting version effective at event time",
                    "Do not conclude relay malfunction without verified settings",
                ]
            )
            return DecisionResult(
                state=DecisionState.INCONCLUSIVE.value,
                confidence=ConfidenceLevel.INCONCLUSIVE.value,
                reasons=reasons,
                recommended_actions=actions,
                requires_engineer_review=True,
            )

        if rca and rca.forced_inconclusive:
            return DecisionResult(
                state=DecisionState.INCONCLUSIVE.value,
                confidence=ConfidenceLevel.INCONCLUSIVE.value,
                reasons=["RCA forced INCONCLUSIVE by consistency policy"],
                recommended_actions=["Engineer review of setting hierarchy required"],
                requires_engineer_review=True,
            )

        primary = rca.primary if rca else None
        if primary and primary.status == "CONFIRMED":
            state = DecisionState.ANALYSIS_COMPLETE.value
            conf = ConfidenceLevel.HIGH.value
            reasons.append(f"Primary hypothesis CONFIRMED: {primary.hypothesis_id}")
        elif primary and primary.status == "PROBABLE":
            state = DecisionState.ANALYSIS_COMPLETE_WITH_WARNINGS.value
            conf = ConfidenceLevel.MEDIUM.value
            reasons.append(f"Primary hypothesis PROBABLE: {primary.hypothesis_id}")
            actions.append("Engineer review recommended before final acceptance")
        elif primary and primary.status in ("POSSIBLE", "INCONCLUSIVE", "UNLIKELY"):
            state = DecisionState.ENGINEER_REVIEW_REQUIRED.value
            conf = ConfidenceLevel.LOW.value
            reasons.append(f"Primary hypothesis {primary.status}: {primary.hypothesis_id}")
            actions.append("Manual engineer review required")
        else:
            state = DecisionState.INCONCLUSIVE.value
            conf = ConfidenceLevel.INCONCLUSIVE.value
            reasons.append("No conclusive RCA hypothesis")

        if warnings:
            reasons.extend(warnings)
            if state == DecisionState.ANALYSIS_COMPLETE.value:
                state = DecisionState.ANALYSIS_COMPLETE_WITH_WARNINGS.value

        if consistency and consistency.summary_status == "INCONSISTENT":
            actions.append("Resolve consistency findings before closing event")
            if state == DecisionState.ANALYSIS_COMPLETE.value:
                state = DecisionState.ANALYSIS_COMPLETE_WITH_WARNINGS.value

        return DecisionResult(
            state=state,
            confidence=conf,
            reasons=reasons,
            recommended_actions=actions,
            requires_engineer_review=state
            in (
                DecisionState.ENGINEER_REVIEW_REQUIRED.value,
                DecisionState.INCONCLUSIVE.value,
            ),
        )
