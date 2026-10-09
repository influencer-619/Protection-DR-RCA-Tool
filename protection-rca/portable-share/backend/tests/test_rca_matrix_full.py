"""Full Excel RCA matrix (54 scenarios) executable in matrix_v1."""

from __future__ import annotations

import json
from pathlib import Path

from rca.matrix import load_matrix, match_matrix, reload_matrix

RULES = Path(__file__).resolve().parents[2] / "rules" / "rca"
EXPORT = RULES / "_excel_matrix_export.json"

# Minimal evidence bags that must uniquely prefer each Excel-mapped scenario id
_BAGS: dict[str, set[str]] = {
    "SC_LBB_CASCADE_COMPOUND": {
        "cascade_lbb_detected",
        "bf_logic_satisfied",
        "current_persists",
        "intertrip_send_observed",
        "fault_classified",
    },
    "SC_SWITCH_ONTO_FAULT": {
        "fault_classified",
        "protection_operated",
        "switch_onto_fault_context",
        "sotf_element_asserted",
    },
    "SC_FEEDER_INZONE": {
        "fault_classified",
        "protection_operated",
        "earth_fault_element_operated",
        "scheme_earth_fault",
        "current_increase_observed",
    },
    "SC_INRUSH_ENERGIZATION_FALLBACK": {
        "magnetizing_inrush_possible",
        "harmonic_evidence",
        "electrical_no_fault",
    },
    "SC_BUS_ZONE_REQUIRES_87B": {"bus_diff_operated", "fault_classified"},
    "SC_XFMR_INTERNAL_THROUGH_EXCLUDED": {
        "differential_operated",
        "through_fault_excluded",
        "fault_classified",
        "transformer_diff_operated",
    },
    "SC_TRANSFORMER_OVERFLUXING_OVEREXCITATION": {
        "overflux_operated",
        "vhz_elevated",
        "protection_operated",
    },
    "SC_MOTOR_LOCKED_ROTOR": {
        "locked_rotor_indicated",
        "motor_stall_indicated",
        "current_increase_observed",
    },
    "SC_MOTOR_LOAD_JAM_DURING_RUNNING": {
        "load_jam_indicated",
        "current_increase_observed",
        "protection_operated",
    },
    "SC_FEEDER_LINE_HIGH_IMPEDANCE_FAULT": {
        "high_impedance_fault_indicated",
        "hif_suspected",
        "earth_fault_element_operated",
    },
    "SC_CAPACITOR_BANK_CAPACITOR_UNBALANCE_INTERNAL_FAULT": {
        "capacitor_unbalance_operated",
        "protection_operated",
    },
    "SC_BREAKER_TRIP_CIRCUIT_FAILURE": {
        "trip_circuit_fail",
        "tc_supervision_alarm",
        "trip_command_observed",
    },
    "SC_INSTRUMENTATION_VT_FAILURE_VOLTAGE_MEASUREMENT_LOSS": {
        "voltage_channel_anomaly",
        "vt_fail_indicated",
    },
    "SC_PROTECTION_PROTECTION_MALOPERATION_UNEXPLAINED_TRIP": {
        "trip_observed",
        "electrical_no_fault",
        "settings_verified",
    },
}


def test_full_matrix_has_all_54_excel_rows():
    reload_matrix()
    m = load_matrix()
    assert m.get("version") == "1.1.0"
    scenarios = m.get("scenarios") or []
    assert len(scenarios) == 54
    assert m.get("source_scenario_count") == 54
    assert len(m.get("lbb_steps") or []) == 10
    export = json.loads(EXPORT.read_text(encoding="utf-8"))
    excel_rows = {s["row"] for s in export["scenarios"]}
    pack_rows = {s.get("excel_row") for s in scenarios}
    assert excel_rows == pack_rows


def test_every_excel_scenario_has_compound_class_and_primary():
    reload_matrix()
    for sc in load_matrix().get("scenarios") or []:
        assert sc.get("id")
        assert sc.get("compound_class")
        assert sc.get("primary_hypothesis")
        assert sc.get("excel_row")
        assert "L1" in (sc.get("levels") or [])


def test_sampled_full_matrix_matches():
    reload_matrix()
    for sid, bag in _BAGS.items():
        r = match_matrix(bag)
        assert r.matched_scenario_id == sid, (
            f"expected {sid}, got {r.matched_scenario_id} "
            f"(candidates={[c.get('id') for c in r.candidates]})"
        )
        assert r.compound_class
        assert r.primary_hypothesis


def test_excel_export_present():
    assert EXPORT.is_file()
    data = json.loads(EXPORT.read_text(encoding="utf-8"))
    assert len(data["scenarios"]) == 54
