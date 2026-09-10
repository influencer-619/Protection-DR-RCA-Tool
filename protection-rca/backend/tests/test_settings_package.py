"""Unit tests for nested relay-settings package flatten / aliases."""

from __future__ import annotations

from app.services.settings_package import (
    canonical_param,
    looks_like_settings_json,
    normalize_relay_settings_package,
)


def test_canonical_aliases():
    assert canonical_param("pickup_a") == "pickup_current"
    assert canonical_param("pickup_a_primary") == "pickup_current"
    assert canonical_param("time_multiplier") == "time_dial"
    assert canonical_param("zone1_reach_ohm") == "zone1_reach"
    assert canonical_param("enabled") == "enabled"


def test_uploaded_settings_auto_approved():
    data = {
        "setting_source": "RELAY_CONFIGURATION",
        "elements": {"51N": {"enabled": True, "pickup_a": 0.3}},
    }
    meta, rows, flat = normalize_relay_settings_package(data)
    assert meta["approval_status"] == "APPROVED"
    assert meta["verified"] is True
    assert "APPROVED" in str(meta["source"]).upper()
    assert flat["approval_status"] == "APPROVED"
    assert flat["active_setting_group_verified"] is True
    assert rows


def test_flatten_elements_package():
    data = {
        "setting_source": "APPROVED_RELAY_BASE_SETTINGS",
        "setting_version": "RS-TEST-2026-001",
        "setting_group": "GROUP-1",
        "active_setting_group_verified": False,
        "elements": {
            "51": {"enabled": True, "pickup_a": 800, "trip_delay_ms": 100},
            "50": {"enabled": True, "pickup_a": 6000},
            "21": {"enabled": True, "zone1_reach_ohm": 15},
        },
    }
    assert looks_like_settings_json("relay_settings.json", data)
    meta, rows, flat = normalize_relay_settings_package(data)
    assert meta["version"] == "RS-TEST-2026-001"
    assert meta["group"] == "GROUP-1"
    assert meta["verified"] is True
    assert meta["source"] == "APPROVED_RELAY_BASE_SETTINGS"
    assert meta["approval_status"] == "APPROVED"

    params_51 = {(e, p): v for e, p, v in rows if e == "51"}
    assert ("51", "enabled") in params_51
    assert params_51[("51", "pickup_current")] == 800
    assert params_51[("51", "pickup_a")] == 800  # original kept
    assert flat["51.pickup_current"] == 800
    assert flat["setting_group"] == "GROUP-1"


def test_flatten_protection_elements_v1():
    data = {
        "schema": "protection-rca.relay-settings.v1",
        "setting_reference": {
            "source": "APPROVED_RELAY_BASE_SETTINGS",
            "version": "RS-TEST-2026-001",
            "group": "GROUP-1",
            "active_setting_group_verified": True,
        },
        "protection_elements": {
            "51": {
                "enabled": True,
                "pickup_a_primary": 800,
                "curve": "IEC_STANDARD_INVERSE",
                "time_multiplier": 0.1,
            },
            "51N": {"enabled": True, "pickup_a_primary": 300},
        },
    }
    meta, rows, _flat = normalize_relay_settings_package(data)
    assert meta["verified"] is True
    assert meta["version"] == "RS-TEST-2026-001"
    by = {(e, p): v for e, p, v in rows}
    assert by[("51", "pickup_current")] == 800
    assert by[("51", "time_dial")] == 0.1
    assert by[("51", "curve")] == "IEC_STANDARD_INVERSE"
    assert by[("51N", "pickup_current")] == 300
