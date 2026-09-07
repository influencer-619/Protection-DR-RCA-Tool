"""Unit tests for COMTRADE parsing, scaling, timestamps, and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from comtrade.parsers.common import parse_cfg, parse_comtrade_datetime
from comtrade.parsers.registry import ComtradeParserRegistry
from comtrade.quality import QualityEngine
from comtrade.scaling import ScalingEngine
from comtrade.service import ComtradeService
from comtrade.timestamps import TimestampEngine
from comtrade.validator import ComtradeValidator
from comtrade.canonical.model import AnalogChannel

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


@pytest.fixture(scope="module")
def parsed_record():
    return ComtradeParserRegistry().parse([CFG, DAT])


def test_parse_cfg_ieee_1999(cfg_text: str):
    cfg = parse_cfg(cfg_text)
    assert cfg.station == "TEST_STATION"
    assert cfg.device == "REL_01"
    assert cfg.revision_year == "1999"
    assert cfg.total_channels == 6
    assert cfg.analog_count == 4
    assert cfg.digital_count == 2
    assert len(cfg.analog_channels) == 4
    assert len(cfg.digital_channels) == 2
    assert cfg.nominal_frequency == 50.0
    assert cfg.nrates == 1
    assert cfg.sample_rates[0].sample_rate_hz == 1000.0
    assert cfg.sample_rates[0].end_sample == 100
    assert cfg.data_format == "ASCII"
    assert cfg.time_multiplier == 1.0
    assert cfg.start_time is not None
    assert cfg.trigger_time is not None

    ia = cfg.analog_channels[0]
    assert ia.name == "Ia"
    assert ia.phase == "A"
    assert ia.a == pytest.approx(0.1)
    assert ia.b == pytest.approx(0.0)
    assert ia.primary == pytest.approx(1000)
    assert ia.secondary == pytest.approx(1)
    assert ia.ps == "P"


def test_parse_comtrade_datetime_dd_mm_yyyy():
    dt = parse_comtrade_datetime("04/09/2026,11:58:00.050000")
    assert dt is not None
    assert dt.day == 4
    assert dt.month == 9
    assert dt.year == 2026
    assert dt.microsecond == 50000


def test_registry_parse_fixture(parsed_record):
    rec = parsed_record
    assert rec.standard == "IEEE"
    assert rec.revision == "1999"
    assert rec.container == "CFG_DAT"
    assert rec.samples == 100
    assert len(rec.timestamps) == 100
    assert rec.timestamps[0] == 0
    assert "Ia" in rec.raw_values
    assert "Ia" in rec.scaled_values
    assert "TRIP" in rec.raw_values
    assert len(rec.scaled_values["Ia"]) == 100


def test_scaling_ag_fault_current(parsed_record):
    """After fault inception (~sample 50), Ia scaled peak should be >> load."""
    ia = parsed_record.scaled_values["Ia"]
    pre = [abs(v) for v in ia[10:40] if v is not None]
    post = [abs(v) for v in ia[60:90] if v is not None]
    assert max(pre) < 500  # load ~200 A peak
    assert max(post) > 1500  # fault ~2500 A peak


def test_scaling_engine_formula():
    eng = ScalingEngine()
    ch = AnalogChannel(index=1, name="Ia", a=0.1, b=2.0, primary=1000, secondary=1, ps="P")
    assert eng.scale_sample(100, ch, apply_ps=False) == pytest.approx(12.0)
    # recorded as P, target P → no ratio change
    assert eng.scale_sample(100, ch, apply_ps=True, target_side="P") == pytest.approx(12.0)
    # convert P→S
    assert eng.scale_sample(100, ch, apply_ps=True, target_side="S") == pytest.approx(12.0 / 1000.0)


def test_timestamp_monotonic(parsed_record):
    ts = TimestampEngine().assess(parsed_record.timestamps, sample_rate_hz=1000.0)
    assert ts.is_monotonic is True
    assert ts.duplicate_count == 0
    assert parsed_record.timestamps[1] == 1000  # 1 ms at 1 kHz


def test_validator_valid(parsed_record):
    result = ComtradeValidator().validate(parsed_record)
    assert result.status in ("VALID", "VALID_WITH_WARNINGS", "PARTIALLY_SUPPORTED")
    assert result.status != "INVALID"
    assert result.checks_passed > 0


def test_validator_detects_length_mismatch(parsed_record):
    bad = parsed_record
    # Shallow copy mutation for test — truncate one series
    original = bad.raw_values["Ia"]
    bad.raw_values["Ia"] = original[:-5]
    try:
        result = ComtradeValidator().validate(bad)
        # Length mismatch is a warning so usable multi-channel records are not discarded
        assert result.status == "VALID_WITH_WARNINGS"
        assert any(i.code == "RAW_LENGTH" and i.severity == "warning" for i in result.issues)
    finally:
        bad.raw_values["Ia"] = original


def test_quality_engine(parsed_record):
    qa = QualityEngine().assess(parsed_record)
    assert qa.overall in ("GOOD", "ACCEPTABLE", "WARNING")
    assert qa.score > 0.5
    assert "Ia" in qa.channel_quality


def test_service_ingest():
    result = ComtradeService().ingest([CFG, DAT])
    assert result.success is True
    assert result.record is not None
    assert result.record.samples == 100
    assert result.detection.revision == "1999"
    assert result.validation is not None
    assert "detect" in result.stages
    assert "parse" in result.stages
    assert "validate" in result.stages


def test_cff_ascii_roundtrip(tmp_path: Path, cfg_text: str):
    dat_text = DAT.read_text(encoding="ascii")
    cff = tmp_path / "ag_fault.cff"
    cff.write_text(
        "--- file type: CFG ---\n"
        + cfg_text
        + "--- file type: DAT ASCII ---\n"
        + dat_text,
        encoding="utf-8",
    )
    rec = ComtradeParserRegistry().parse([cff])
    assert rec.container == "CFF"
    assert rec.samples == 100
    assert rec.revision in ("1999", "2013")


def test_binary_dat_parse(tmp_path: Path, cfg_text: str):
    """Build a tiny BINARY DAT and parse via pipeline."""
    import struct

    from comtrade.parsers._pipeline import RecordBuilder
    from comtrade.parsers.common import parse_cfg

    # Minimal 1A 0D CFG forced to BINARY
    cfg_bin = (
        "STN,DEV,1999\n"
        "1,1A,0D\n"
        "1,Ia,A,,A,1.0,0.0,0,-32767,32767,1,1,P\n"
        "50\n1\n1000.0,3\n"
        "01/01/2020,00:00:00.000000\n"
        "01/01/2020,00:00:00.001000\n"
        "BINARY\n1\n"
    )
    cfg_path = tmp_path / "mini.cfg"
    dat_path = tmp_path / "mini.dat"
    cfg_path.write_text(cfg_bin, encoding="ascii")

    records = b""
    for i in range(3):
        records += struct.pack("<ii", i + 1, i * 1000)
        records += struct.pack("<h", 100 * (i + 1))
    dat_path.write_bytes(records)

    rec = RecordBuilder().parse_cfg_dat_files(
        cfg_path, dat_path, standard="IEEE", revision="1999"
    )
    assert rec.samples == 3
    assert rec.data_format == "BINARY"
    assert rec.scaled_values["Ia"][0] == pytest.approx(100.0)
    assert rec.scaled_values["Ia"][2] == pytest.approx(300.0)


def test_never_silently_repairs_missing_sample():
    eng = ScalingEngine()
    ch = AnalogChannel(index=1, name="Ia", a=1.0, b=0.0)
    assert eng.scale_sample(None, ch) is None


def test_ascii_dat_timestamp_first_no_sample_number(tmp_path: Path):
    """Vendor ASCII form: timestamp,A…,D… (1+Na+Nd) must not shift digitals."""
    from comtrade.parsers.ascii.parser import AsciiDatParser
    from comtrade.parsers.common import parse_cfg

    cfg_text = (
        "STN,DEV,1999\n"
        "4,2A,2D\n"
        "1,VA,A,,V,1,0,0,-1e9,1e9,1,1,P\n"
        "2,IA,A,,A,1,0,0,-1e9,1e9,1,1,P\n"
        "1,50_PICKUP,,,\n"
        "2,51_PICKUP,,,\n"
        "50\n1\n5000,3\n"
        "01/01/2026,00:00:00.000000\n"
        "01/01/2026,00:00:00.000000\n"
        "ASCII\n1\n"
    )
    cfg = parse_cfg(cfg_text)
    # 1+2+2 = 5 fields: t, VA, IA, d50, d51
    dat_text = (
        "0.00000000,100.0,1.0,0,0\n"
        "0.00020000,110.0,2.0,1,0\n"
        "0.00040000,120.0,3.0,1,0\n"
    )
    parsed = AsciiDatParser().parse(dat_text, cfg)
    assert parsed.sample_count == 3
    assert parsed.analog_raw["VA"] == [100.0, 110.0, 120.0]
    assert parsed.analog_raw["IA"] == [1.0, 2.0, 3.0]
    assert parsed.digital_raw["50_PICKUP"] == [0, 1, 1]
    assert parsed.digital_raw["51_PICKUP"] == [0, 0, 0]
    # seconds → µs storage
    assert parsed.timestamps == [0, 200, 400]

    # End-to-end through service
    cfg_path = tmp_path / "tf.cfg"
    dat_path = tmp_path / "tf.dat"
    cfg_path.write_text(cfg_text, encoding="ascii")
    dat_path.write_text(dat_text, encoding="ascii")
    rec = ComtradeService().parse([cfg_path, dat_path])
    assert rec.samples == 3
    assert rec.raw_values["50_PICKUP"][1] == 1
    assert rec.raw_values["51_PICKUP"][1] == 0

