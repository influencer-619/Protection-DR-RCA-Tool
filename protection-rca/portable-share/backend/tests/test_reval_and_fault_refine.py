"""REVAL ingest + digital phase / orphan-trip refinements."""

from __future__ import annotations

from pathlib import Path

import pytest

from comtrade import ComtradeService
from comtrade.parsers.reval import is_reval, parse_reval
from fault_analysis import _phase_hint_from_names, _refine_with_digital_phase
from protection.channel_ansi import match_ansi_from_channel
from protection.engine import observations_from_timeline
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
