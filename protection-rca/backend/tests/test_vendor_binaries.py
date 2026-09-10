"""Tests for SEL .rdb, SEL .cev, and DIGSI/PCM600 package bridges."""

from __future__ import annotations

import io
import zipfile
from unittest.mock import MagicMock, patch

from app.services.file_service import infer_source_type
from app.services.settings_ingest import ingest_settings_bytes
from app.services.vendor_formats import (
    cev_to_comtrade_files,
    expand_vendor_package,
    extract_sel_rdb_text,
    is_ole2,
    is_vendor_package,
)


def test_infer_vendor_package_extensions():
    assert infer_source_type("project.dz5") == "PACKAGE"
    assert infer_source_type("device.dex5") == "PACKAGE"
    assert infer_source_type("event.cev") == "COMTRADE"
    assert infer_source_type("relay.rdb") == "SETTINGS"


def test_digsi_zip_package_extracts_comtrade():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "records/fault.cfg",
            "TEST,REL,1999\n2,1A,1D\n1,Ia,A,,A,1,0,0,-1,1,1,1,P\n1,TRIP,,,0\n50\n1\n1000,2\n"
            "01/01/2024,00:00:00.000000\n01/01/2024,00:00:00.001000\nASCII\n1\n",
        )
        zf.writestr("records/fault.dat", "1,0,10,0\n2,1000,20,1\n")
        zf.writestr("junk/readme.bin", b"\x00\x01\x02")
    data = buf.getvalue()
    assert is_vendor_package("site.dz5", data)
    out = expand_vendor_package(data, filename="site.dz5")
    assert out["status"] == "OK"
    names = {m["filename"] for m in out["members"]}
    assert "fault.cfg" in names
    assert "fault.dat" in names
    assert "readme.bin" not in names


def test_non_zip_dz5_not_calculable():
    out = expand_vendor_package(b"NOTAZIP", filename="project.dz5")
    assert out["status"] == "NOT_CALCULABLE"
    assert "COMTRADE" in (out.get("reason") or "") or "ZIP" in (out.get("reason") or "")


def test_rdb_non_ole_rejected():
    assert not is_ole2(b"hello")
    r = extract_sel_rdb_text(b"hello")
    assert r["status"] == "NOT_CALCULABLE"


def test_rdb_ole_extracts_set_all_text():
    set_all = """[FID]
FID=SEL-421-R123
[SET_1]
E51S=Y
51SP=1.5
51STD=2.0
CTR=600
"""
    ole_magic = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64

    mock_ole = MagicMock()
    mock_ole.listdir.return_value = [("SET_ALL",)]
    stream = MagicMock()
    stream.read.return_value = set_all.encode("utf-8")
    mock_ole.openstream.return_value = stream

    with patch("olefile.OleFileIO", return_value=mock_ole):
        extracted = extract_sel_rdb_text(ole_magic)
    assert extracted["status"] == "OK"
    assert "51SP" in extracted["text"]

    with patch("olefile.OleFileIO", return_value=mock_ole):
        ingested = ingest_settings_bytes(ole_magic, filename="relay.rdb")
    assert ingested["status"] == "OK"
    assert ingested["vendor"] == "SEL"
    assert ingested["param_count"] > 0


def test_cev_conversion_uses_pycev_when_available():
    """When pycev parses, we emit CFG+DAT; otherwise NOT_CALCULABLE with reason."""
    class _FakeCev:
        analog_count = 1
        digital_count = 1
        analog_channels = [[0.0, 100.0, 200.0]]
        digital_channels = [[0, 0, 1]]
        analog_channel_ids = ["IA"]
        digital_channel_ids = ["TRIP"]
        frequency = 50.0
        fid = "FID=SEL-421-TEST"
        settings = "E51S=Y\n51SP=1.0\n"
        trigger_time = __import__("datetime").datetime(2024, 1, 15, 12, 0, 0)
        time = [
            __import__("datetime").datetime(2024, 1, 15, 11, 59, 59, 998000),
            __import__("datetime").datetime(2024, 1, 15, 11, 59, 59, 999000),
            __import__("datetime").datetime(2024, 1, 15, 12, 0, 0, 0),
        ]
        _properties = {"SAM/CYC_A": "8"}

        def __init__(self, *a, **k):
            pass

    with patch.dict("sys.modules", {"pycev": MagicMock(CEV=_FakeCev)}):
        # Force re-import path inside function — patch pycev.CEV used by import
        with patch("pycev.CEV", _FakeCev):
            out = cev_to_comtrade_files(b"FID=SEL dummy", basename="event.cev")
    assert out["status"] == "OK"
    assert "IA" in out["cfg"]
    assert out["dat"].count("\n") >= 3
    assert out["samples"] == 3


def test_cev_missing_pycev_message():
    with patch.dict("sys.modules", {"pycev": None}):
        # Simulate ImportError inside function
        import builtins

        real_import = builtins.__import__

        def _imp(name, *a, **k):
            if name == "pycev" or name.startswith("pycev."):
                raise ImportError("no pycev")
            return real_import(name, *a, **k)

        with patch("builtins.__import__", side_effect=_imp):
            out = cev_to_comtrade_files(b"x", basename="e.cev")
    assert out["status"] == "NOT_CALCULABLE"
    assert "pycev" in (out.get("reason") or "").lower()
