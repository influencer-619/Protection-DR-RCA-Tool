"""Tests for RIO/XRIO distance zone parsing and harmonics STFT heatmap."""

from __future__ import annotations

import numpy as np
import pytest

from settings.rio_zones import extract_distance_zones, parse_rio_text, zones_from_settings_flat
from signal_processing.harmonics import compute_harmonics_stft

FS = 4000.0
F0 = 50.0


SAMPLE_RIO_MHO = """
BEGIN DISTANCE
LINEANGLE 75
BEGIN ZONE
LABEL "Z1"
INDEX 1
ACTIVE TRUE
BEGIN MHOSHAPE
REACH 8.5
ANGLE 75
END MHOSHAPE
END ZONE
BEGIN ZONE
LABEL "Z2"
INDEX 2
ACTIVE TRUE
BEGIN MHOSHAPE
REACH 12.0
ANGLE 75
END MHOSHAPE
END ZONE
END DISTANCE
"""

SAMPLE_RIO_POLYGON = """
BEGIN DISTANCE
LINEANGLE 80
BEGIN ZONE
LABEL "Z1P"
INDEX 1
ACTIVE TRUE
BEGIN SHAPE
LINE 0, 0, 90
LINE 5, 0, 0
LINE 5, 8, -90
LINE 0, 8, 180
END SHAPE
END ZONE
END DISTANCE
"""


def test_parse_rio_mho_zones():
    zones = parse_rio_text(SAMPLE_RIO_MHO)
    assert len(zones) == 2
    assert zones[0]["shape"] == "mho"
    assert zones[0]["label"] == "Z1"
    assert zones[0]["reach_ohm"] == pytest.approx(8.5)
    assert zones[0]["radius_ohm"] is not None and zones[0]["radius_ohm"] > 0
    assert zones[0]["center_r"] is not None
    assert zones[1]["reach_ohm"] == pytest.approx(12.0)
    assert zones[0]["source"] == "rio_mho"


def test_parse_rio_polygon_zone():
    zones = parse_rio_text(SAMPLE_RIO_POLYGON)
    assert len(zones) == 1
    assert zones[0]["shape"] == "polygon"
    poly = zones[0]["polygon"]
    assert isinstance(poly, list) and len(poly) >= 3
    assert all("r" in p and "x" in p for p in poly)


def test_settings_fallback_mho():
    zones = zones_from_settings_flat(
        {"21": {"z1_reach_ohm": 10.0, "z2_reach_ohm": 15.0, "zone1_angle": 70.0}}
    )
    assert len(zones) == 2
    assert zones[0]["label"] == "Z1"
    assert zones[0]["reach_ohm"] == pytest.approx(10.0)
    assert zones[0]["angle_deg"] == pytest.approx(70.0)


def test_extract_prefers_rio_over_settings():
    zones = extract_distance_zones(
        file_texts=[("zone.rio", SAMPLE_RIO_MHO)],
        relay_settings={"21": {"z1_reach_ohm": 99.0}},
    )
    assert len(zones) == 2
    assert zones[0]["reach_ohm"] == pytest.approx(8.5)


def test_extract_settings_when_no_rio():
    zones = extract_distance_zones(
        file_texts=[],
        relay_settings={"21": {"reach_ohm": 7.5}},
    )
    assert len(zones) == 1
    assert zones[0]["reach_ohm"] == pytest.approx(7.5)


def test_harmonics_stft_heatmap_shape():
    n = int(FS / F0) * 8
    t = np.arange(n) / FS
    x = (
        100.0 * np.sqrt(2) * np.sin(2 * np.pi * F0 * t)
        + 20.0 * np.sqrt(2) * np.sin(2 * np.pi * 3 * F0 * t)
    )
    out = compute_harmonics_stft(
        x,
        sample_rate_hz=FS,
        channel="IA",
        nominal_frequency_hz=F0,
        max_harmonic=7,
        max_frames=16,
        unit="A",
    )
    assert out["status"] == "OK"
    assert len(out["times_s"]) >= 2
    assert "1" in out["harmonics_rms"] and "3" in out["harmonics_rms"]
    assert len(out["harmonics_rms"]["1"]) == len(out["times_s"])
    h1 = float(np.mean(out["harmonics_rms"]["1"]))
    h3 = float(np.mean(out["harmonics_rms"]["3"]))
    assert h1 > h3 > 0


def test_harmonics_stft_empty():
    out = compute_harmonics_stft([], sample_rate_hz=FS, channel="IA")
    assert out["status"] == "NOT_CALCULABLE"
