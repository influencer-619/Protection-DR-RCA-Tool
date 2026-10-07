"""MiCOM Courier .set and DIGSI4 .dex package bridges."""

from __future__ import annotations

from pathlib import Path

from app.services.file_service import infer_source_type
from app.services.settings_ingest import ingest_settings_bytes, setting_records_from_ingested
from app.services.settings_micom_courier import is_micom_courier_set, parse_micom_courier_set
from app.services.vendor_formats import expand_vendor_package, is_vendor_package

BINA = Path(r"C:\Users\5863.AVAADA\Downloads\DR Files\Files From Bina Mam")


def _skip_if_missing(path: Path):
    if not path.exists():
        import pytest

        pytest.skip(f"Sample not present: {path}")


def test_micom_courier_set_maps_protection_and_ct():
    path = BINA / "P143_UNIT_TIE_SET_PSL" / "P143.set"
    _skip_if_missing(path)
    data = path.read_bytes()
    assert is_micom_courier_set(data, path.name)
    parsed = parse_micom_courier_set(data, filename=path.name)
    assert parsed["status"] == "OK"
    assert parsed["vendor"] == "SCHNEIDER"
    prot = (parsed.get("mapped") or {}).get("protection") or {}
    assert "51" in prot
    assert prot["51"].get("pickup_current") == 1.8
    assert abs(float(prot["51"].get("time_dial", 0)) - 0.16) < 1e-9
    ct = (parsed.get("mapped") or {}).get("ct_vt") or {}
    assert ct.get("ct_primary_a") == 2500.0
    assert ct.get("ct_secondary_a") == 1.0
    assert ct.get("ct_ratio") == 2500.0
    assert ct.get("vt_primary_v") == 6600.0
    assert ct.get("vt_secondary_v") == 110.0
    device = (parsed.get("mapped") or {}).get("device") or {}
    assert device.get("plant_reference") == "UNIT STATION TIE"
    assert device.get("frequency_hz") == 50.0
    flat, records = setting_records_from_ingested(parsed)
    assert records
    assert any(r.element in ("51", "50", "51N", "50BF") for r in records)


def test_ingest_settings_bytes_routes_micom_set():
    path = BINA / "P 241_MOTOR_SET_PSL" / "P241_900KW.set"
    _skip_if_missing(path)
    ing = ingest_settings_bytes(path.read_bytes(), filename=path.name)
    assert ing["status"] == "OK"
    assert ing["vendor"] == "SCHNEIDER"
    assert ing.get("param_count", 0) > 5
    ct = (ing.get("mapped") or {}).get("ct_vt") or {}
    assert ct.get("ct_secondary_a") == 1.0
    assert ct.get("ct_primary_a") == 200.0
    device = (ing.get("mapped") or {}).get("device") or {}
    assert "900KW" in (device.get("plant_reference") or "")


def test_digsi4_dex_expands_nested_comtrade():
    path = BINA / "TR2_TRIPPING_211208" / "7UT613 V4.6 _ARY_TR2.dex"
    _skip_if_missing(path)
    data = path.read_bytes()
    assert is_vendor_package(path.name, data)
    assert infer_source_type(path.name) == "PACKAGE"
    expanded = expand_vendor_package(data, filename=path.name)
    assert expanded["status"] == "OK"
    kinds = {m["kind"] for m in expanded["members"]}
    names = [m["filename"].lower() for m in expanded["members"]]
    assert "COMTRADE" in kinds
    assert any(n.endswith(".cfg") for n in names)
    assert any(n.endswith(".dat") for n in names)
    assert any("digsi_info" in n for n in names)
