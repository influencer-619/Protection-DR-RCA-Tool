"""Unit tests for COMTRADE format/version/container detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from comtrade.detector.container_detector import ComtradeContainerDetector
from comtrade.detector.data_format_detector import ComtradeDataFormatDetector
from comtrade.detector.format_detector import ComtradeFormatDetector
from comtrade.detector.service import ComtradeDetectionService
from comtrade.detector.version_detector import ComtradeVersionDetector

FIXTURE_DIR = (
    Path(__file__).resolve().parents[2]
    / "test_data"
    / "comtrade"
    / "ieee_1999"
)
CFG = FIXTURE_DIR / "ag_fault.cfg"
DAT = FIXTURE_DIR / "ag_fault.dat"


@pytest.fixture(scope="module")
def cfg_text() -> str:
    return CFG.read_text(encoding="ascii")


def test_fixtures_exist():
    assert CFG.is_file(), f"missing fixture {CFG}"
    assert DAT.is_file(), f"missing fixture {DAT}"


def test_format_detector_cfg_dat():
    det = ComtradeFormatDetector().detect([CFG, DAT])
    assert det.is_comtrade is True
    assert det.cfg_path is not None
    assert det.dat_path is not None
    assert det.confidence >= 0.5


def test_format_detector_rejects_non_comtrade(tmp_path: Path):
    junk = tmp_path / "notes.txt"
    junk.write_text("hello world\nnot a comtrade file\n", encoding="utf-8")
    det = ComtradeFormatDetector().detect([junk])
    assert det.is_comtrade is False or det.confidence < 0.5


def test_version_detector_1999(cfg_text: str):
    v = ComtradeVersionDetector().detect(cfg_text)
    assert v.revision == "1999"
    assert v.standard == "IEEE"
    assert v.year_field == "1999"
    assert v.confidence >= 0.5


def test_version_detector_2013_markers():
    cfg = (
        "STN,DEV,2013\n"
        "1,1A,0D\n"
        "1,Ia,A,,A,1,0,0,-1,1,1,1,P\n"
        "50\n1\n1000,10\n"
        "01/01/2020,00:00:00.000000\n"
        "01/01/2020,00:00:00.001000\n"
        "FLOAT32\n1\n0,0\n0,0\n"
    )
    v = ComtradeVersionDetector().detect(cfg)
    assert v.revision == "2013"


def test_version_detector_1991_no_year():
    cfg = (
        "STN,DEV\n"
        "1,1A,0D\n"
        "1,Ia,A,,A,1,0,0,-1,1\n"
        "50\n1\n1000,10\n"
        "01/01/1991,00:00:00.000000\n"
        "01/01/1991,00:00:00.001000\n"
        "ASCII\n1\n"
    )
    v = ComtradeVersionDetector().detect(cfg)
    assert v.revision == "1991"


def test_container_detector_cfg_dat():
    c = ComtradeContainerDetector().detect([CFG, DAT])
    assert c.container == "CFG_DAT"
    assert c.cfg_path is not None
    assert c.dat_path is not None


def test_container_detector_cff(tmp_path: Path):
    cff = tmp_path / "rec.cff"
    cff.write_text(
        "--- file type: CFG ---\n"
        "STN,DEV,2013\n1,1A,0D\n1,Ia,A,,A,1,0,0,-1,1,1,1,P\n"
        "50\n1\n1000,2\n01/01/2020,00:00:00.000000\n"
        "01/01/2020,00:00:00.001000\nASCII\n1\n"
        "--- file type: DAT ASCII ---\n"
        "1,0,100\n2,1000,110\n",
        encoding="utf-8",
    )
    c = ComtradeContainerDetector().detect([cff])
    assert c.container == "CFF"
    assert c.cff_path is not None


def test_data_format_from_cfg(cfg_text: str):
    d = ComtradeDataFormatDetector().detect_from_cfg(cfg_text)
    assert d.data_format == "ASCII"
    assert d.confidence >= 0.8


def test_data_format_from_dat_content():
    d = ComtradeDataFormatDetector().detect_from_dat(DAT)
    assert d.data_format == "ASCII"


def test_detection_service_end_to_end():
    result = ComtradeDetectionService().detect([CFG, DAT])
    assert result.is_comtrade is True
    assert result.standard == "IEEE"
    assert result.revision == "1999"
    assert result.container == "CFG_DAT"
    assert result.data_format == "ASCII"
    assert result.status in ("SUPPORTED", "PARTIALLY_SUPPORTED")
    assert result.confidence > 0.5
    # Must be content-based — paths recorded
    assert result.cfg_path is not None
    assert result.dat_path is not None


def test_detection_inspects_content_not_just_extension(tmp_path: Path):
    """Misnamed files should still be detected via content when possible."""
    weird = tmp_path / "record.bin"
    weird.write_text(CFG.read_text(encoding="ascii"), encoding="ascii")
    dat_copy = tmp_path / "record.dat"
    dat_copy.write_text(DAT.read_text(encoding="ascii"), encoding="ascii")
    # With only misnamed CFG-like + DAT, format detector should still find CFG content
    fmt = ComtradeFormatDetector().detect([weird, dat_copy])
    assert fmt.is_comtrade or fmt.confidence >= 0.5 or fmt.cfg_path is not None
