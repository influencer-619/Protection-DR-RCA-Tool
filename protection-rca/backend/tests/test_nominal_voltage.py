"""Nominal voltage extraction from settings / VT / names."""

from __future__ import annotations

from app.services.param_detect import extract_nominal_voltage_kv


def test_extract_from_settings_text():
    text = """
    Nominal System Voltage    : 132 kV
    Nominal Frequency         : 50 Hz
    VT Ratio                  : 132000/110 V
    """
    kv, src = extract_nominal_voltage_kv(texts=[text])
    assert kv == 132.0
    assert src and "nominal" in src


def test_extract_from_vt_ratio_json():
    kv, src = extract_nominal_voltage_kv(
        json_blobs=[{"vt_ratio": "132000/110", "site": "Avaada"}]
    )
    assert kv == 132.0
    assert src and "vt" in src


def test_extract_from_filename():
    kv, src = extract_nominal_voltage_kv(filenames=["EVT-AG-132KV-FEEDER-001.cfg"])
    assert kv == 132.0
    assert src and "filename" in src


def test_extract_from_station_name():
    kv, src = extract_nominal_voltage_kv(station="Avaada 132kV Substation - Feeder Bay 1")
    assert kv == 132.0
    assert src and "station" in src


def test_no_invent_without_evidence():
    kv, src = extract_nominal_voltage_kv(
        texts=["Relay trip at 0.333 s"],
        filenames=["event.cfg"],
        station="UNKNOWN",
    )
    assert kv is None
    assert src is None
