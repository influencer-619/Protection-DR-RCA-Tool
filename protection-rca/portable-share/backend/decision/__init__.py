"""Final decision engine — never forces a conclusion."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from app.core.enums import DecisionState, ConfidenceLevel
from consistency.engine import ConsistencyResult
from rca import RCAResult


# Limitations that are expected / non-blocking for a CONFIRMED plant-fault RCA.
_INFORMATIONAL_SUBSTRINGS = (
    "not_applicable",
    "not applicable",
    "not available",
    "not in scope",
    "fault distance",
    "z1/km",
    "line-location",
    "no distance",
    "loop_ab:",
    "loop_bc:",
    "loop_ca:",
    "loop_ag:",
    "loop_bg:",
    "loop_cg:",
    "phase_a power",
    "phase_b power",
    "phase_c power",
    "missing v/i for",
    "partially_supported",
    "merged",  # SOE / event-report timeline merge notes
    "external timeline",
    "soe / event report",
    "from soe",
)

# Limitations that should keep CONFIRMED analyses in WITH_WARNINGS.
_MATERIAL_SUBSTRINGS = (
    "ct saturation",
    "magnetizing inrush",
    "data quality",
    "invalid",
    "setting inconsistency",
    "unverified setting",
    "active setting",
    "polarity",
    "insufficient disturbance",
    "unsupported",
    "critical",
    "cfg+dat",
    "comtrade ingest",
)


def is_material_decision_warning(text: str) -> bool:
    """True when a limitation should downgrade ANALYSIS_COMPLETE → WITH_WARNINGS."""
    s = str(text or "").strip().lower()
    if not s:
        return False
    if any(tok in s for tok in _INFORMATIONAL_SUBSTRINGS):
        # Explicit material cues still win (e.g. "INVALID — NOT AVAILABLE")
        if any(tok in s for tok in ("ct saturation", "magnetizing inrush", "setting inconsistency")):
            return True
        return False
    if any(tok in s for tok in _MATERIAL_SUBSTRINGS):
        return True
    # Unknown limitation → treat as material so we don't hide real issues
    return True


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

        material = [w for w in warnings if is_material_decision_warning(w)]
        informational = [w for w in warnings if w not in material]

        if material:
            reasons.extend(material[:5])
            if state == DecisionState.ANALYSIS_COMPLETE.value:
                state = DecisionState.ANALYSIS_COMPLETE_WITH_WARNINGS.value
        elif informational and state == DecisionState.ANALYSIS_COMPLETE.value:
            # Keep CONFIRMED → ANALYSIS_COMPLETE; note non-blocking limits once
            reasons.append(
                f"Non-blocking limitation (does not change decision): {informational[0]}"
            )

        if consistency and consistency.summary_status == "INCONSISTENT":
            actions.append("Resolve consistency findings before closing event")
            if state == DecisionState.ANALYSIS_COMPLETE.value:
                state = DecisionState.ANALYSIS_COMPLETE_WITH_WARNINGS.value
                reasons.append("Consistency findings include INCONSISTENT checks")

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
