"""REVAL ingest + digital phase / orphan-trip refinements."""

from __future__ import annotations

from pathlib import Path

import pytest

from comtrade import ComtradeService
from comtrade.parsers.reval import is_reval, parse_reval
from fault_analysis import (
    _phase_hint_from_names,
    _phases_from_names,
    _refine_with_digital_phase,
    _refine_with_digital_phases,
    classify_fault,
)
from electrical_analysis.analyzer import ElectricalAnalysisResult
from protection.channel_ansi import match_ansi_from_channel
from protection.engine import observations_from_timeline
from protection.models import ProtectionAssessment
from event_reconstruction.timeline import TimelineEvent


BINA = Path(r"C:\Users\5863.AVAADA\Downloads\DR Files\Files From Bina Mam")


@pytest.mark.skipif(not BINA.is_dir(), reason="Bina Mam DR folder not present")
def test_reval_mumbai_ingests():
    reh = next(BINA.rglob("DHNU2_one.REH"))
    assert is_reval([reh])
    rec = parse_reval([reh])
    assert rec.samples > 0
    assert any(c.name == "DIFF TRIP" for c in rec.digital_channels)
    ing = ComtradeService().ingest([reh])
    assert ing.success and ing.record is not None


def test_diff_trip_is_line_diff_not_xfmr():
    assert match_ansi_from_channel("DIFF TRIP") == "87L"
    assert match_ansi_from_channel("B DIFF TRIP") == "87L"
    assert match_ansi_from_channel("Diff> TRIP") == "87T"


def test_phase_hint_indian_ryb():
    assert _phase_hint_from_names(["VERS B PH TRIP"]) == "C"
    assert _phase_hint_from_names(["BOIS R PH TRIP"]) == "A"
    ft, st, _ = _refine_with_digital_phase(
        "ABC", "CLASSIFIED", "MEDIUM", {"ground": False}, "C"
    )
    assert ft == "CG"
    assert st == "PROBABLE"


def test_phases_from_western_and_soe_labels():
    assert _phases_from_names(["Trip A", "PhA TRIP"]) == {"A"}
    assert _phases_from_names(["50A", "IA>"]) == {"A"}
    assert _phases_from_names(["A-G FAULT", "51N"]) == {"A"}
    assert _phases_from_names(["TRIP A", "TRIP B"]) == {"A", "B"}
    assert _phases_from_names(["ABC FAULT"]) == {"A", "B", "C"}
    ft, st, _ = _refine_with_digital_phases(
        "UNKNOWN", "UNKNOWN", "INCONCLUSIVE", {"ground": True}, {"A", "B"}
    )
    assert ft == "ABG"
    assert st == "CLASSIFIED"


def test_classify_from_digitals_when_currents_unmapped():
    """No IA/IB/IC map — still type AG from SOE/digital phase + earth element."""
    elec = ElectricalAnalysisResult(
        record_id="r-dig",
        nominal_frequency_hz=50.0,
        sample_rate_hz=4000.0,
    )
    tl = [
        TimelineEvent(
            timestamp=0.05,
            event_type="protection_trip",
            source="digital:Ph A Trip",
            confidence="HIGH",
            metadata={},
        ),
        TimelineEvent(
            timestamp=0.06,
            event_type="protection_trip",
            source="SOE:51N Earth Fault",
            confidence="HIGH",
            metadata={"signal": "51N Earth Fault", "element": "51N"},
        ),
    ]
    assessments = [
        ProtectionAssessment(
            element="51N",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="TRIPPED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            confidence="MEDIUM",
            evidence_ids=["digital:51N Earth Fault", "digital:Ph A Trip"],
        )
    ]
    r = classify_fault(elec, timeline=tl, assessments=assessments)
    assert r.fault_type == "AG"
    assert r.status in ("CLASSIFIED", "PROBABLE")


def test_orphan_trip_does_not_invent_oc_from_electrical_alone():
    """Opaque trip contact + electrical fault must NOT invent 50/51 without pickup evidence."""
    tl = [
        TimelineEvent(
            timestamp=0.1,
            event_type="protection_trip",
            source="digital:Relay 1 (Trip)",
            confidence="HIGH",
            metadata={},
        )
    ]
    obs = observations_from_timeline(
        tl, electrical={"trip_command": True, "fault_indicated": True}
    )
    assert "50" not in obs
    assert "51" not in obs
