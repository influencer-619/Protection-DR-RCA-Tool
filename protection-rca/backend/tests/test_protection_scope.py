"""Protection/consistency scoped to uploaded settings + COMTRADE digitals."""

from __future__ import annotations

from event_reconstruction.timeline import TimelineEvent
from protection.engine import ProtectionRuleEngine, elements_from_uploaded_files
from settings.hierarchy.resolver import SettingRecord, SettingSource


def _rec(element: str, parameter: str = "enabled", value=True) -> SettingRecord:
    return SettingRecord(
        setting_id=f"t-{element}-{parameter}",
        relay_id="R1",
        setting_group="G1",
        parameter=parameter,
        value=value,
        enabled=True if parameter == "enabled" else None,
        version="v1",
        source=SettingSource.APPROVED_RELAY_BASE,
        approval_status="APPROVED",
        verified=True,
        element=element,
    )


def test_elements_from_uploaded_files_prefers_settings_digital_overlap():
    cands = [_rec("21"), _rec("51"), _rec("GENERAL", "nominal_freq", 50)]
    codes = elements_from_uploaded_files(
        timeline=[],
        setting_candidates=cands,
        digital_channel_names=["21_Z1_PICKUP", "51_TRIP", "86_LOCKOUT", "IA"],
    )
    # Digitals present → only settings∩digitals (skip 86 settings-less noise)
    assert codes == ["21", "51"]


def test_elements_from_digitals_when_no_settings_overlap():
    codes = elements_from_uploaded_files(
        timeline=[],
        setting_candidates=[_rec("27")],
        digital_channel_names=["21_Z1_PICKUP", "51_TRIP"],
    )
    assert codes == ["21", "51"]


def test_assess_does_not_use_full_catalog():
    engine = ProtectionRuleEngine()
    timeline = [
        TimelineEvent(
            timestamp=0.4,
            event_type="protection_pickup",
            source="digital:21_Z1_PICKUP",
            confidence="HIGH",
        )
    ]
    result = engine.assess(
        timeline=timeline,
        setting_candidates=[_rec("21"), _rec("51")],
        digital_channel_names=["21_Z1_PICKUP", "51_TRIP"],
    )
    assessed = {a.element for a in result.assessments}
    assert assessed == {"21", "51"}
    assert "87T" not in assessed
    assert "27" not in assessed
    assert len(result.assessments) == 2
