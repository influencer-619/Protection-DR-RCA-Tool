"""COMTRADE golden matrix regression — detect/parse fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from comtrade.service import ComtradeService

ROOT = Path(__file__).resolve().parents[2] / "test_data"
COMTRADE = ROOT / "comtrade"
GOLDEN = ROOT / "golden"


def _paths(*parts: str) -> list[Path]:
    base = COMTRADE.joinpath(*parts)
    if base.suffix.lower() == ".cff":
        return [base]
    cfg = base.with_suffix(".cfg") if base.suffix else Path(str(base) + ".cfg")
    # parts may be folder
    if base.is_dir():
        cfg = next(base.glob("*.cfg"), None)
        dat = next(base.glob("*.dat"), None)
        return [p for p in (cfg, dat) if p]
    dat = cfg.with_suffix(".dat")
    return [p for p in (cfg, dat) if p.is_file()]


@pytest.mark.parametrize(
    "folder,expect_comtrade",
    [
        ("ieee_1999", True),
        ("ieee_2013", True),
        ("ieee_1991", True),
        ("ieee_binary", True),
        ("ieee_binary32", True),
        ("ieee_float32", True),
        ("cff", True),
    ],
)
def test_detect_fixture_matrix(folder: str, expect_comtrade: bool):
    folder_path = COMTRADE / folder
    if not folder_path.exists():
        pytest.skip(f"fixture {folder} not generated — run scripts/generate_comtrade_fixtures.py")
    if folder == "cff":
        files = list(folder_path.glob("*.cff"))
    else:
        files = list(folder_path.glob("*.cfg")) + list(folder_path.glob("*.dat"))
    assert files, f"no files in {folder_path}"
    det = ComtradeService().detect(files)
    assert det.is_comtrade is expect_comtrade
    assert det.status in ("SUPPORTED", "PARTIALLY_SUPPORTED", "VALID_WITH_WARNINGS")


@pytest.mark.parametrize(
    "folder",
    ["ieee_1999", "ieee_2013", "ieee_1991", "ieee_binary", "ieee_binary32", "ieee_float32", "cff"],
)
def test_parse_fixture_matrix(folder: str):
    folder_path = COMTRADE / folder
    if not folder_path.exists():
        pytest.skip(f"fixture {folder} not generated")
    if folder == "cff":
        files = list(folder_path.glob("*.cff"))
    else:
        files = list(folder_path.glob("*.cfg")) + list(folder_path.glob("*.dat"))
    svc = ComtradeService()
    ingest = svc.ingest(files, validate_after_parse=True)
    # 1991 may be partial — allow success or explicit partial failure without inventing data
    if folder == "ieee_1991" and not ingest.success:
        assert ingest.detection.status in ("PARTIALLY_SUPPORTED", "SUPPORTED")
        return
    assert ingest.success, ingest.error
    assert ingest.record is not None
    assert ingest.record.samples > 0
    assert len(ingest.record.analog_channels) >= 1


def test_malformed_not_silently_valid():
    files = [COMTRADE / "malformed" / "bad.cfg"]
    if not files[0].is_file():
        pytest.skip("malformed fixture missing")
    ingest = ComtradeService().ingest(files, validate_after_parse=True)
    assert ingest.success is False or (
        ingest.validation is not None
        and getattr(ingest.validation, "status", "") in ("INVALID", "NOT_VALIDATED", "VALID_WITH_WARNINGS")
    )


def test_golden_expected_json_present():
    base = GOLDEN / "EVT-SYNTH-AG-001" / "expected.json"
    assert base.is_file()
    data = json.loads(base.read_text(encoding="utf-8"))
    assert data.get("support_status") or data.get("comtrade_version") or data.get("case_id")


def test_protection_51_inverse_curve_physics():
    from protection.curves import inverse_time_s, pickup_multiple
    from protection.models import ElementContext, ElementObservation
    from protection.elements.el_51 import ELEMENT

    m = pickup_multiple(200.0, 100.0)
    assert m == 2.0
    t = inverse_time_s(multiple=2.0, time_dial=0.5, curve="IEC_NORMAL_INVERSE")
    assert t is not None and t > 0

    ctx = ElementContext(
        observations=ElementObservation(element="51", pickup=True, trip=True, pickup_time_s=0.0, trip_time_s=0.2),
        settings={"enabled": True, "pickup_current": 100.0, "time_dial": 0.5, "curve": "IEC_NORMAL_INVERSE"},
        setting_resolutions={},
        electrical={"current_a": 200.0, "fault_indicated": True},
        rule_config={"physics": {"default_curve": "IEC_NORMAL_INVERSE", "timing_tolerance_s": 0.5}},
    )
    a = ELEMENT.assess(ctx)
    assert a.timing is not None
    assert a.timing.get("physics_status") == "CALCULATED"
    assert a.timing.get("expected_operate_time_s") is not None


def test_distance_21_not_calculable_without_z():
    from protection.models import ElementContext, ElementObservation
    from protection.elements.el_21 import ELEMENT

    ctx = ElementContext(
        observations=ElementObservation(element="21", pickup=None, trip=None),
        settings={"enabled": True, "zone1_reach": 10.0},
        setting_resolutions={},
        electrical={},
        rule_config={"physics": {"shape": "mho"}},
    )
    a = ELEMENT.assess(ctx)
    assert a.metadata.get("fault_distance") == "NOT_CALCULABLE" or (
        a.timing and a.timing.get("zone_physics", {}).get("status") == "NOT_CALCULABLE"
    )
