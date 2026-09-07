"""CT/VT / line parameter flexible detection (no fixed field wording required)."""

from __future__ import annotations

from app.services.param_detect import detect_plant_parameters
from app.services.side_files import line_ct_vt_from_settings_data
from fault_analysis.location import normalize_ct_vt, parse_ratio_value


def test_parse_ratio_slash_strings():
    assert parse_ratio_value("800/1") == 800.0
    assert abs(parse_ratio_value("132000/110") - (132000 / 110)) < 1e-9
    assert parse_ratio_value(800) == 800.0
    assert parse_ratio_value("bad") is None


def test_normalize_ct_vt_from_slash_strings():
    out = normalize_ct_vt({"ct_ratio": "800/1", "vt_ratio": "132000/110"})
    assert out["ct_ratio"] == 800.0
    assert abs(out["vt_ratio"] - (132000 / 110)) < 1e-9
    assert out["ct_primary_a"] == 800.0
    assert out["ct_secondary_a"] == 1.0


def test_line_ct_vt_from_flat_settings_json():
    line, ct_vt = line_ct_vt_from_settings_data(
        {
            "site": "Avaada 132kV Substation - Feeder Bay 1",
            "relay_model": "Multifunction Numerical Feeder/Bus Protection Relay",
            "ct_ratio": "800/1",
            "vt_ratio": "132000/110",
        }
    )
    assert line == {}
    assert ct_vt.get("ct_ratio") == 800.0
    assert abs(float(ct_vt["vt_ratio"]) - (132000 / 110)) < 1e-9


def test_detect_alternate_wordings_nested():
    """Vendor JSON with different labels / nesting still maps CT/VT + line."""
    det = detect_plant_parameters(
        {
            "Plant": {
                "CTR": "800/1",
                "VT Ratio": "132000/110",
            },
            "Feeder data": {
                "Line Length (km)": 24.5,
                "Positive Sequence R (ohm/km)": 0.12,
                "Positive Sequence X (ohm/km)": 0.38,
                "R0 ohm/km": 0.35,
                "X0": 1.1,
            },
        }
    )
    assert det["ct_vt"]["ct_ratio"] == 800.0
    assert abs(det["ct_vt"]["vt_ratio"] - (132000 / 110)) < 1e-9
    assert det["line"]["length_km"] == 24.5
    assert det["line"]["positive_sequence_r_ohm_per_km"] == 0.12
    assert det["line"]["positive_sequence_x_ohm_per_km"] == 0.38
    assert det["detected_keys"]


def test_detect_pt_alias_and_primary_secondary():
    det = detect_plant_parameters(
        {
            "CT Primary A": 800,
            "CT Secondary": 1,
            "PT ratio": "132kV/110V",  # may fail parse — use slash without letters
            "PT_Ratio": "132000/110",
        }
    )
    assert det["ct_vt"]["ct_ratio"] == 800.0
    assert abs(det["ct_vt"]["vt_ratio"] - (132000 / 110)) < 1e-9
