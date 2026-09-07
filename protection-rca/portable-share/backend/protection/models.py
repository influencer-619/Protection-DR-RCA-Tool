"""Protection assessment models and base element interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class ProtectionAssessment:
    element: str
    enabled: Optional[bool]
    pickup: Optional[bool]
    trip: Optional[bool]
    expected_operation: str  # OPERATE | NOT_OPERATE | UNKNOWN
    actual_operation: str  # OPERATED | NOT_OPERATED | UNKNOWN
    timing: Optional[dict[str, Any]]
    consistency: str  # CONSISTENT | INCONSISTENT | UNVERIFIABLE | DATA_QUALITY_ISSUE
    setting_reference: dict[str, Any]
    evidence_ids: list[str] = field(default_factory=list)
    confidence: str = "INCONCLUSIVE"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ElementObservation:
    """Observed digital/analog behavior for an element."""

    element: str
    pickup: Optional[bool] = None
    trip: Optional[bool] = None
    pickup_time_s: Optional[float] = None
    trip_time_s: Optional[float] = None
    direction: Optional[str] = None
    zone: Optional[int] = None
    channel_evidence: list[str] = field(default_factory=list)


@dataclass
class ElementContext:
    observations: ElementObservation
    settings: dict[str, Any]  # resolved setting values
    setting_resolutions: dict[str, Any]
    electrical: dict[str, Any] = field(default_factory=dict)
    timeline: list[dict[str, Any]] = field(default_factory=list)
    rule_config: dict[str, Any] = field(default_factory=dict)


class ProtectionElement(ABC):
    element_code: str = ""

    @abstractmethod
    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        ...


def _expected_from_settings(enabled: Optional[bool], electrical_fault: bool) -> str:
    if enabled is None:
        return "UNKNOWN"
    if not enabled:
        return "NOT_OPERATE"
    if electrical_fault:
        return "OPERATE"
    return "UNKNOWN"


def _actual(pickup: Optional[bool], trip: Optional[bool]) -> str:
    if trip is True or pickup is True:
        return "OPERATED"
    if trip is False and pickup is False:
        return "NOT_OPERATED"
    if trip is None and pickup is None:
        return "UNKNOWN"
    if trip is False and pickup is None:
        return "NOT_OPERATED"
    if pickup is False and trip is None:
        return "NOT_OPERATED"
    return "UNKNOWN"


def base_assess(
    element: str,
    ctx: ElementContext,
    *,
    electrical_fault_hint: bool = False,
) -> ProtectionAssessment:
    """Shared assessment logic used by element modules."""
    obs = ctx.observations
    enabled = ctx.settings.get("enabled")
    if enabled is None and "enabled" in ctx.setting_resolutions:
        res = ctx.setting_resolutions["enabled"]
        enabled = getattr(res, "enabled", None)
        if enabled is None:
            enabled = getattr(res, "value", None)

    expected = _expected_from_settings(
        enabled if isinstance(enabled, bool) else None, electrical_fault_hint
    )
    actual = _actual(obs.pickup, obs.trip)

    # Consistency prelim (detailed checks in consistency engine)
    consistency = "UNVERIFIABLE"
    if isinstance(enabled, bool):
        if enabled is False and (obs.pickup is True or obs.trip is True):
            consistency = "INCONSISTENT"
        elif enabled is True and obs.trip is True and obs.pickup is False:
            consistency = "INCONSISTENT"
        elif enabled is True and (obs.pickup is not None or obs.trip is not None):
            consistency = "CONSISTENT"
        elif enabled is False and obs.pickup is False and obs.trip is False:
            consistency = "CONSISTENT"

    setting_ref = {
        k: (v.to_dict() if hasattr(v, "to_dict") else v)
        for k, v in ctx.setting_resolutions.items()
    }

    timing = None
    if obs.pickup_time_s is not None or obs.trip_time_s is not None:
        timing = {
            "pickup_time_s": obs.pickup_time_s,
            "trip_time_s": obs.trip_time_s,
            "operate_time_s": (
                (obs.trip_time_s - obs.pickup_time_s)
                if obs.pickup_time_s is not None and obs.trip_time_s is not None
                else None
            ),
        }

    conf = "MEDIUM"
    if consistency == "UNVERIFIABLE" or actual == "UNKNOWN":
        conf = "INCONCLUSIVE"
    elif consistency == "INCONSISTENT":
        conf = "LOW"

    return ProtectionAssessment(
        element=element,
        enabled=enabled if isinstance(enabled, bool) else None,
        pickup=obs.pickup,
        trip=obs.trip,
        expected_operation=expected,
        actual_operation=actual,
        timing=timing,
        consistency=consistency,
        setting_reference=setting_ref,
        evidence_ids=list(obs.channel_evidence),
        confidence=conf,
        metadata={"zone": obs.zone, "direction": obs.direction},
    )
