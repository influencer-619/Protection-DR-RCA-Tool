"""Settings hierarchy resolution — never silently chooses a source."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class SettingSource(str, Enum):
    EVENT_SPECIFIC_ACTIVE = "EVENT_SPECIFIC_ACTIVE"
    ACTIVE_SETTING_GROUP = "ACTIVE_SETTING_GROUP"
    APPROVED_RELAY_BASE = "APPROVED_RELAY_BASE"
    RELAY_CONFIGURATION = "RELAY_CONFIGURATION"
    HISTORICAL = "HISTORICAL"
    ENGINEERING_DESIGN = "ENGINEERING_DESIGN"
    NONE = "NONE"


# Priority order (1 = highest)
SOURCE_PRIORITY: list[SettingSource] = [
    SettingSource.EVENT_SPECIFIC_ACTIVE,
    SettingSource.ACTIVE_SETTING_GROUP,
    SettingSource.APPROVED_RELAY_BASE,
    SettingSource.RELAY_CONFIGURATION,
    SettingSource.HISTORICAL,
    SettingSource.ENGINEERING_DESIGN,
]


class VerificationStatus(str, Enum):
    VERIFIED = "VERIFIED"
    NOT_VERIFIED = "NOT_VERIFIED"


@dataclass
class SettingRecord:
    """One parameter from a candidate setting package."""

    setting_id: str
    relay_id: str
    setting_group: str
    parameter: str
    value: Any
    unit: str = ""
    enabled: Optional[bool] = None
    effective_from: Optional[str] = None
    effective_to: Optional[str] = None
    version: str = ""
    source: SettingSource = SettingSource.APPROVED_RELAY_BASE
    approval_status: str = "DRAFT"
    verified: bool = False
    element: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["source"] = self.source.value
        return d


@dataclass
class SettingResolution:
    """Explicit resolution outcome — never silent."""

    parameter: str
    element: str
    value: Any
    unit: str
    enabled: Optional[bool]
    source: str
    version: str
    group: str
    verification_status: str
    candidates_considered: list[str] = field(default_factory=list)
    explanation: str = ""
    setting_id: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def resolve_setting(
    parameter: str,
    candidates: list[SettingRecord],
    *,
    element: str = "",
    require_verified_for_active: bool = True,
) -> SettingResolution:
    """
    Resolve a setting parameter using the mandated hierarchy.

    Never silently chooses: always returns SettingResolution with source,
    version, group, and verification_status.
    """
    matching = [c for c in candidates if c.parameter == parameter]
    if element:
        matching = [c for c in matching if not c.element or c.element == element]

    considered = [f"{c.source.value}:{c.version}:{c.setting_group}" for c in matching]

    if not matching:
        return SettingResolution(
            parameter=parameter,
            element=element,
            value=None,
            unit="",
            enabled=None,
            source=SettingSource.NONE.value,
            version="NOT AVAILABLE",
            group="NOT AVAILABLE",
            verification_status=VerificationStatus.NOT_VERIFIED.value,
            candidates_considered=considered,
            explanation="No setting candidate available for this parameter",
        )

    by_source: dict[SettingSource, list[SettingRecord]] = {}
    for c in matching:
        by_source.setdefault(c.source, []).append(c)

    chosen: Optional[SettingRecord] = None
    for src in SOURCE_PRIORITY:
        opts = by_source.get(src) or []
        if not opts:
            continue
        # Prefer verified / approved
        preferred = [o for o in opts if o.verified or o.approval_status == "APPROVED"]
        pool = preferred or opts
        chosen = pool[0]
        break

    if chosen is None:
        return SettingResolution(
            parameter=parameter,
            element=element,
            value=None,
            unit="",
            enabled=None,
            source=SettingSource.NONE.value,
            version="NOT AVAILABLE",
            group="NOT AVAILABLE",
            verification_status=VerificationStatus.NOT_VERIFIED.value,
            candidates_considered=considered,
            explanation="Candidates present but none matched hierarchy sources",
        )

    verified = chosen.verified or (
        chosen.source == SettingSource.EVENT_SPECIFIC_ACTIVE and chosen.verified
    )
    # Active group / event-specific require explicit verification flag
    if require_verified_for_active and chosen.source in (
        SettingSource.EVENT_SPECIFIC_ACTIVE,
        SettingSource.ACTIVE_SETTING_GROUP,
    ):
        vstatus = (
            VerificationStatus.VERIFIED.value
            if chosen.verified
            else VerificationStatus.NOT_VERIFIED.value
        )
    else:
        vstatus = (
            VerificationStatus.VERIFIED.value
            if (chosen.verified or chosen.approval_status == "APPROVED")
            else VerificationStatus.NOT_VERIFIED.value
        )

    return SettingResolution(
        parameter=parameter,
        element=element or chosen.element,
        value=chosen.value,
        unit=chosen.unit,
        enabled=chosen.enabled,
        source=chosen.source.value,
        version=chosen.version or "UNKNOWN",
        group=chosen.setting_group or "UNKNOWN",
        verification_status=vstatus,
        candidates_considered=considered,
        explanation=(
            f"Setting source used: {chosen.source.value}; "
            f"version={chosen.version}; group={chosen.setting_group}; "
            f"verification={vstatus}"
        ),
        setting_id=chosen.setting_id,
    )


def resolve_element_settings(
    element: str,
    parameters: list[str],
    candidates: list[SettingRecord],
) -> dict[str, SettingResolution]:
    """Resolve multiple parameters for one protection element."""
    return {
        p: resolve_setting(p, candidates, element=element) for p in parameters
    }
