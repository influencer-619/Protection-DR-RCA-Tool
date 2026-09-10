"""Phase A/B/C unit tests — channel map, 87/67/BF physics, two-ended, settings ingest."""

from __future__ import annotations

import math

from common.results import SignalResult
from electrical_analysis.analyzer import ElectricalAnalysisResult
from electrical_analysis.detectors import detect_ct_saturation, detect_magnetizing_inrush
from fault_analysis.location import compute_fault_locations, locate_two_ended
from protection.physics import breaker_failure_timing, differential_operate_restraint, directional_67
from app.services.settings_ingest import ingest_settings_bytes, map_common_protection_params
from app.services.folder_watch import scan_ingest_folder


def _sr(value, unit="A"):
    return SignalResult(
        value=value,
        unit=unit,
        timestamp=None,
        method="test",
        algorithm_version="test",
        input_channels=[],
        quality="GOOD",
        status="OK",
    )


def _elec_stub(roles, phasors, harmonics=None, rms=None, peak=None):
    elec = ElectricalAnalysisResult(
        record_id="t",
        nominal_frequency_hz=50.0,
        sample_rate_hz=4000.0,
    )
    elec.channel_roles = roles
    for ch, cval in phasors.items():
        elec.phasors[ch] = _sr(
            {"real": cval.real, "imag": cval.imag, "magnitude": abs(cval), "angle_deg": 0.0}
        )
    if harmonics:
        for ch, hmap in harmonics.items():
            elec.harmonics[ch] = _sr({"harmonics_rms": hmap, "thd_percent": 20.0})
    if rms:
        for ch, v in rms.items():
            elec.rms[ch] = _sr(v)
    if peak:
        for ch, v in peak.items():
            elec.peak[ch] = _sr(v)
    return elec


def test_differential_operate_internal():
    r = differential_operate_restraint(i_local=10 + 0j, i_remote=10 + 0j, slope=0.3, pickup_a=0.2)
    assert r["status"] == "OK"
    assert r["operate_expected"] is False
    r2 = differential_operate_restraint(i_local=10 + 0j, i_remote=-10 + 0j, slope=0.3, pickup_a=0.2)
    assert r2["operate_expected"] is True


def test_directional_67_forward():
    import cmath

    v = cmath.rect(100, 0)
    i = cmath.rect(10, math.radians(-45))
    d = directional_67(i_fault=i, v_polarize=v, max_torque_angle_deg=-45.0)
    assert d["status"] == "OK"
    assert d["direction"] == "FORWARD"


def test_breaker_failure_timing():
    t = breaker_failure_timing(
        trip_time_s=0.1,
        current_drop_time_s=0.35,
        bf_timer_s=0.15,
        current_persists=False,
    )
    assert t["status"] == "OK"
    assert t["bf_expected"] is True


def test_ct_sat_and_inrush_detectors():
    elec = _elec_stub(
        {"Ia": "IA"},
        {"Ia": 5 + 0j},
        harmonics={"Ia": {"1": 5.0, "2": 1.5, "3": 0.2}},
        rms={"Ia": 5.0},
        peak={"Ia": 20.0},
    )
    sat = detect_ct_saturation(elec)
    assert sat["status"] == "POSSIBLE"
    inrush = detect_magnetizing_inrush(elec)
    assert inrush["status"] == "POSSIBLE"


def test_two_ended_location():
    local = _elec_stub({"Ia": "IA", "Va": "VA"}, {"Ia": 100 + 0j, "Va": 50 + 40j})
    local.impedance["phase_A"] = _sr({"R": 2.0, "X": 4.0}, unit="ohm")
    remote = _elec_stub({"Ia": "IA", "Va": "VA"}, {"Ia": 80 + 0j, "Va": 30 + 20j})
    remote.impedance["phase_A"] = _sr({"R": 1.5, "X": 3.0}, unit="ohm")
    row = locate_two_ended(
        local,
        remote,
        fault_type="AG",
        z1_per_km=complex(0.1, 0.4),
        length_km=50.0,
        sync_offset_us=0.0,
    )
    assert row["status"] == "OK"
    assert row["distance_km"] is not None

    out = compute_fault_locations(
        local,
        fault_type="AG",
        line_params={
            "length_km": 50.0,
            "positive_sequence_r_ohm_per_km": 0.1,
            "positive_sequence_x_ohm_per_km": 0.4,
        },
        elec_remote=remote,
        sync_offset_us=0.0,
    )
    assert out["two_ended"] is True
    assert any(a["algorithm"].startswith("Two-Ended") for a in out["algorithms"])


def test_settings_ingest_kv():
    raw = b"pickup=1.2\nct_ratio=800/1\nvt_ratio=132000/110\nlength_km=42\nz1_r=0.1\nz1_x=0.4\n"
    res = ingest_settings_bytes(raw, filename="relay_settings.txt")
    assert res["status"] == "OK"
    assert "ct_ratio" in res["common"] or "ct_ratio" in res["mapped"].get("ct_vt", {})
    assert "length_km" in res["common"] or "length_km" in res["mapped"].get("line", {})


def test_map_common_params():
    m = map_common_protection_params({"pickup_a": 1.0, "bf_timer_s": 0.2, "mta_deg": -30})
    assert m["pickup_a"] == 1.0
    assert m["bf_timer_s"] == 0.2


def test_folder_scan_missing():
    r = scan_ingest_folder("/nonexistent/path/xyz")
    assert r["status"] == "NOT_AVAILABLE"
