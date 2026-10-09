"""Generate rules/rca/matrix_v1.yaml from Excel export (all 54 scenarios)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPORT = ROOT / "rules" / "rca" / "_excel_matrix_export.json"
OUT = ROOT / "rules" / "rca" / "matrix_v1.yaml"


def _slug(asset: str, scenario: str) -> str:
    raw = f"{asset}_{scenario}"
    raw = re.sub(r"[^A-Za-z0-9]+", "_", raw).strip("_").upper()
    return f"SC_{raw}"[:72]


# Hand-mapped tokens / primary / priority for each Excel scenario title
# Keys: (asset, scenario) exact from export
MAP: dict[tuple[str, str], dict] = {
    ("Transformer", "Normal energization"): {
        "priority": 92,
        "prefer_primary": True,
        "required_any": ["magnetizing_inrush_possible", "switching_event_correlated", "dfr_non_fault_event"],
        "supporting_any": ["harmonic_evidence", "electrical_no_fault", "breaker_close_observed"],
        "forbid": ["trip_observed", "fault_classified_strong"],
        "primary_hypothesis": "SWITCHING_TRANSIENT",
    },
    ("Transformer", "Energization inrush"): {
        "priority": 93,
        "prefer_primary": True,
        "required_any": ["magnetizing_inrush_possible", "harmonic_evidence"],
        "supporting_any": ["switching_event_correlated", "electrical_no_fault", "dfr_non_fault_event"],
        "forbid": ["trip_observed"],
        "primary_hypothesis": "SWITCHING_TRANSIENT",
    },
    ("Transformer", "Internal phase fault"): {
        "priority": 86,
        "prefer_primary": True,
        "required": ["differential_operated", "through_fault_excluded"],
        "supporting_any": ["fault_classified", "transformer_diff_operated", "protection_operated"],
        "forbid": ["magnetizing_inrush_possible"],
        "primary_hypothesis": "TRANSFORMER_INTERNAL_FAULT",
    },
    ("Transformer", "Internal earth fault"): {
        "priority": 86,
        "prefer_primary": True,
        "required": ["fault_classified", "differential_operated"],
        "supporting_any": [
            "earth_fault_element_operated",
            "through_fault_excluded",
            "transformer_diff_operated",
            "protection_operated",
        ],
        "forbid": ["magnetizing_inrush_possible"],
        "primary_hypothesis": "TRANSFORMER_INTERNAL_FAULT",
    },
    ("Transformer", "External through fault"): {
        "priority": 84,
        "prefer_primary": True,
        "required_any": ["through_fault_indicated", "external_through_fault"],
        "supporting_any": ["fault_classified", "protection_operated", "current_increase_observed"],
        "forbid": ["through_fault_excluded"],
        "primary_hypothesis": "EXTERNAL_GRID_DISTURBANCE",
        "fallback_hypothesis": "EXTERNAL_LINE_FAULT",
    },
    ("Transformer", "Differential operation caused by CT saturation / measurement issue"): {
        "priority": 87,
        "prefer_primary": True,
        "required_any": ["ct_saturation_suspected", "waveform_distortion"],
        "supporting_any": ["harmonic_evidence", "differential_operated"],
        "primary_hypothesis": "CT_SATURATION",
    },
    ("Transformer", "Overfluxing / overexcitation"): {
        "priority": 82,
        "prefer_primary": True,
        "required_any": ["overflux_operated", "vhz_elevated"],
        "supporting_any": ["protection_operated", "frequency_anomaly"],
        "primary_hypothesis": "OVEREXCITATION",
    },
    ("Transformer", "Thermal overload"): {
        "priority": 75,
        "prefer_primary": True,
        "required_any": ["thermal_overload_operated", "thermal_overload_indicated"],
        "supporting_any": ["protection_operated"],
        "forbid": ["fault_classified_strong"],
        "primary_hypothesis": "THERMAL_OVERLOAD",
    },
    ("Motor", "Normal starting"): {
        "priority": 91,
        "prefer_primary": True,
        "required": ["motor_start_possible"],
        "supporting_any": ["switching_event_correlated", "electrical_no_fault"],
        "forbid": ["trip_observed", "locked_rotor_indicated"],
        "primary_hypothesis": "MOTOR_START",
    },
    ("Motor", "Prolonged starting"): {
        "priority": 90,
        "prefer_primary": True,
        "required": ["motor_start_possible"],
        "supporting_any": ["prolonged_start_indicated", "thermal_overload_indicated"],
        "primary_hypothesis": "MOTOR_START",
    },
    ("Motor", "Locked rotor"): {
        "priority": 89,
        "prefer_primary": True,
        "required_any": ["locked_rotor_indicated", "motor_stall_indicated"],
        "supporting_any": ["motor_start_possible", "current_increase_observed"],
        "primary_hypothesis": "MOTOR_LOCKED_ROTOR",
    },
    ("Motor", "Load jam during running"): {
        "priority": 88,
        "prefer_primary": True,
        "required_any": ["load_jam_indicated", "motor_stall_indicated"],
        "supporting_any": ["current_increase_observed", "protection_operated"],
        "primary_hypothesis": "MOTOR_LOAD_JAM",
    },
    ("Motor", "Thermal overload"): {
        "priority": 76,
        "prefer_primary": True,
        "required_any": ["thermal_overload_operated", "thermal_overload_indicated"],
        "supporting_any": ["motor_start_possible"],
        "primary_hypothesis": "THERMAL_OVERLOAD",
    },
    ("Motor", "Phase loss / discontinuity"): {
        "priority": 80,
        "prefer_primary": True,
        "required_any": ["phase_loss_indicated", "open_phase_indicated"],
        "supporting_any": ["negative_sequence_elevated", "protection_operated"],
        "primary_hypothesis": "PHASE_LOSS",
    },
    ("Motor", "Negative-sequence unbalance"): {
        "priority": 78,
        "prefer_primary": True,
        "required_any": ["negative_sequence_elevated", "unbalance_protection_operated"],
        "supporting_any": ["protection_operated"],
        "primary_hypothesis": "NEGATIVE_SEQUENCE",
    },
    ("Motor", "Internal phase fault"): {
        "priority": 85,
        "prefer_primary": True,
        "required": ["fault_classified", "protection_operated"],
        "required_any": ["motor_internal_fault_indicated", "motor_diff_operated"],
        "supporting_any": ["current_increase_observed", "overcurrent_element_operated"],
        "forbid": ["motor_start_possible"],
        "primary_hypothesis": "INTERNAL_FEEDER_FAULT",
    },
    ("Motor", "Internal earth fault"): {
        "priority": 85,
        "prefer_primary": True,
        "required": ["fault_classified", "protection_operated"],
        "required_any": ["motor_internal_fault_indicated", "motor_diff_operated"],
        "supporting_any": ["earth_fault_element_operated", "scheme_earth_fault"],
        "forbid": ["motor_start_possible"],
        "primary_hypothesis": "INTERNAL_FEEDER_FAULT",
    },
    ("Feeder/Line", "Phase-earth in-zone fault"): {
        "priority": 82,
        "prefer_primary": False,
        "required": ["fault_classified", "protection_operated"],
        "required_any": ["earth_fault_element_operated", "scheme_earth_fault"],
        "supporting_any": ["current_increase_observed", "overcurrent_element_operated"],
        "forbid": [
            "cascade_lbb_detected",
            "differential_operated",
            "bus_diff_operated",
            "switch_onto_fault_context",
            "transformer_diff_operated",
            "motor_internal_fault_indicated",
        ],
        "primary_hypothesis": "INTERNAL_FEEDER_FAULT",
    },
    ("Feeder/Line", "Phase-phase in-zone fault"): {
        "priority": 81,
        "prefer_primary": False,
        "required": ["fault_classified", "protection_operated"],
        "required_any": ["overcurrent_element_operated", "scheme_overcurrent"],
        "supporting_any": ["current_increase_observed"],
        "forbid": [
            "cascade_lbb_detected",
            "bus_diff_operated",
            "switch_onto_fault_context",
            "earth_fault_element_operated",
            "motor_internal_fault_indicated",
        ],
        "primary_hypothesis": "INTERNAL_FEEDER_FAULT",
    },
    ("Feeder/Line", "Three-phase in-zone fault"): {
        "priority": 80,
        "prefer_primary": False,
        "required": ["fault_classified", "protection_operated"],
        "required_any": ["scheme_distance", "line_diff_operated", "overcurrent_element_operated"],
        "supporting_any": ["current_increase_observed"],
        "forbid": [
            "cascade_lbb_detected",
            "bus_diff_operated",
            "earth_fault_element_operated",
            "motor_internal_fault_indicated",
        ],
        "primary_hypothesis": "EXTERNAL_LINE_FAULT",
        "fallback_hypothesis": "INTERNAL_FEEDER_FAULT",
    },
    ("Feeder/Line", "External / out-of-zone fault"): {
        "priority": 79,
        "prefer_primary": True,
        "required_any": ["out_of_zone_indicated", "external_through_fault"],
        "supporting_any": ["fault_classified", "protection_operated", "scheme_distance"],
        "primary_hypothesis": "EXTERNAL_LINE_FAULT",
    },
    ("Feeder/Line", "High-impedance fault"): {
        "priority": 83,
        "prefer_primary": True,
        "required_any": ["high_impedance_fault_indicated", "hif_suspected"],
        "supporting_any": ["earth_fault_element_operated", "fault_classified", "intermittent_earth_indicated"],
        "primary_hypothesis": "HIGH_IMPEDANCE_FAULT",
    },
    ("Feeder/Line", "Intermittent / transient earth fault"): {
        "priority": 77,
        "prefer_primary": True,
        "required_any": ["intermittent_earth_indicated", "transient_earth_indicated"],
        "supporting_any": ["earth_fault_element_operated", "fault_classified"],
        "primary_hypothesis": "INTERMITTENT_EARTH_FAULT",
    },
    ("Feeder/Line", "Temporary fault cleared by autoreclose"): {
        "priority": 74,
        "prefer_primary": True,
        "required_any": ["autoreclose_success", "reclose_successful"],
        "supporting_any": ["fault_classified", "protection_operated", "trip_observed"],
        "primary_hypothesis": "TEMPORARY_FAULT_RECLOSE",
    },
    ("Feeder/Line", "Persistent fault after autoreclose"): {
        "priority": 74,
        "prefer_primary": True,
        "required_any": ["autoreclose_fail", "reclose_unsuccessful"],
        "supporting_any": ["fault_classified", "protection_operated", "current_persists"],
        "primary_hypothesis": "PERSISTENT_FAULT_RECLOSE",
    },
    ("Feeder/Line", "Switch onto fault"): {
        "priority": 88,
        "prefer_primary": True,
        "required": ["fault_classified", "protection_operated", "switch_onto_fault_context"],
        "supporting_any": ["sotf_element_asserted", "breaker_close_observed", "current_increase_observed"],
        "forbid": ["cascade_lbb_detected", "magnetizing_inrush_possible"],
        "primary_hypothesis": "SWITCH_ONTO_FAULT",
    },
    ("Busbar", "Internal bus fault"): {
        "priority": 88,
        "prefer_primary": True,
        "required": ["bus_diff_operated", "fault_classified"],
        "supporting_any": ["protection_operated"],
        "primary_hypothesis": "BUS_ZONE_FAULT",
    },
    ("Busbar", "External feeder fault with bus restraint"): {
        "priority": 80,
        "prefer_primary": True,
        "required_any": ["bus_restraint_external", "external_feeder_fault_bus_restrain"],
        "supporting_any": ["fault_classified", "protection_operated"],
        "forbid": ["bus_diff_operated"],
        "primary_hypothesis": "INTERNAL_FEEDER_FAULT",
        "fallback_hypothesis": "EXTERNAL_LINE_FAULT",
    },
    ("Busbar", "Bus differential false operation / CT issue"): {
        "priority": 86,
        "prefer_primary": True,
        "required_any": ["bus_diff_operated", "ct_saturation_suspected"],
        "supporting_any": ["waveform_distortion", "electrical_no_fault"],
        "primary_hypothesis": "CT_SATURATION",
        "fallback_hypothesis": "RELAY_MISOPERATION",
    },
    ("Generator", "Internal stator phase fault"): {
        "priority": 86,
        "prefer_primary": True,
        "required": ["generator_diff_operated", "fault_classified"],
        "supporting_any": ["protection_operated"],
        "primary_hypothesis": "GENERATOR_INTERNAL_FAULT",
    },
    ("Generator", "Stator earth fault"): {
        "priority": 85,
        "prefer_primary": True,
        "required_any": ["generator_diff_operated", "stator_earth_operated"],
        "supporting_any": ["fault_classified", "earth_fault_element_operated"],
        "primary_hypothesis": "GENERATOR_INTERNAL_FAULT",
    },
    ("Generator", "Loss of excitation / underexcitation"): {
        "priority": 82,
        "prefer_primary": True,
        "required_any": ["loss_of_excitation_operated", "underexcitation_indicated"],
        "supporting_any": ["protection_operated"],
        "primary_hypothesis": "LOSS_OF_EXCITATION",
    },
    ("Generator", "Negative-sequence heating"): {
        "priority": 78,
        "prefer_primary": True,
        "required_any": ["negative_sequence_elevated", "unbalance_protection_operated"],
        "primary_hypothesis": "NEGATIVE_SEQUENCE",
    },
    ("Generator", "Under/overfrequency"): {
        "priority": 77,
        "prefer_primary": True,
        "required_any": ["frequency_protection_operated", "frequency_anomaly"],
        "primary_hypothesis": "FREQUENCY_EVENT",
    },
    ("Generator", "Out-of-step / pole slip"): {
        "priority": 84,
        "prefer_primary": True,
        "required_any": ["out_of_step_operated", "pole_slip_indicated"],
        "primary_hypothesis": "OUT_OF_STEP",
    },
    ("Generator", "Accidental energization"): {
        "priority": 87,
        "prefer_primary": True,
        "required_any": ["accidental_energization_indicated", "generator_offline_energized"],
        "supporting_any": ["breaker_close_observed", "protection_operated"],
        "primary_hypothesis": "ACCIDENTAL_ENERGIZATION",
    },
    ("Generator", "Overfluxing"): {
        "priority": 82,
        "prefer_primary": True,
        "required_any": ["overflux_operated", "vhz_elevated"],
        "primary_hypothesis": "OVEREXCITATION",
    },
    ("Capacitor Bank", "Normal switching transient"): {
        "priority": 90,
        "prefer_primary": True,
        "required_any": ["switching_event_correlated", "capacitor_switching_indicated"],
        "supporting_any": ["electrical_no_fault", "dfr_non_fault_event"],
        "forbid": ["trip_observed"],
        "primary_hypothesis": "SWITCHING_TRANSIENT",
    },
    ("Capacitor Bank", "Capacitor unbalance / internal fault"): {
        "priority": 83,
        "prefer_primary": True,
        "required_any": ["capacitor_unbalance_operated", "capacitor_fault_indicated"],
        "supporting_any": ["protection_operated", "fault_classified"],
        "primary_hypothesis": "CAPACITOR_BANK_FAULT",
    },
    ("Capacitor Bank", "Overvoltage"): {
        "priority": 76,
        "prefer_primary": True,
        "required_any": ["overvoltage_operated", "overvoltage_indicated"],
        "primary_hypothesis": "OVERVOLTAGE",
    },
    ("Breaker", "Normal successful operation"): {
        "priority": 60,
        "prefer_primary": False,
        "required_any": ["breaker_open_confirmed", "successful_clearing"],
        "forbid": ["current_persists", "bf_logic_satisfied", "cascade_lbb_detected"],
        "primary_hypothesis": "EXTERNAL_LINE_FAULT",
        "fallback_note": "Successful breaker open — classify electrical cause separately",
    },
    ("Breaker", "Breaker fails to open after trip"): {
        "priority": 98,
        "prefer_primary": True,
        "required_any": ["bf_logic_satisfied", "cascade_lbb_detected"],
        "supporting_any": ["current_persists", "trip_command_observed", "intertrip_send_observed"],
        "forbid": ["bus_diff_operated"],
        "primary_hypothesis": "BREAKER_FAILURE",
        "fallback_hypothesis": "INTERTRIP_OPERATION",
        "fallback_when_missing": ["current_persists"],
    },
    ("Breaker", "Trip circuit failure"): {
        "priority": 85,
        "prefer_primary": True,
        "required_any": ["trip_circuit_fail", "tc_supervision_alarm"],
        "supporting_any": ["trip_command_observed", "breaker_failed_to_open"],
        "primary_hypothesis": "TRIP_CIRCUIT_FAILURE",
    },
    ("Breaker", "Breaker stuck / mechanical failure"): {
        "priority": 84,
        "prefer_primary": True,
        "required_any": ["breaker_stuck", "breaker_mechanical_fail"],
        "supporting_any": ["current_persists", "trip_command_observed"],
        "primary_hypothesis": "BREAKER_MECHANICAL_FAILURE",
        "fallback_hypothesis": "BREAKER_FAILURE",
    },
    ("System", "Local Breaker Backup / LBB cascade clearing"): {
        "priority": 100,
        "prefer_primary": True,
        "required_any": ["cascade_lbb_detected", "bf_logic_satisfied"],
        "supporting_any": [
            "intertrip_send_observed",
            "intertrip_receive_observed",
            "intertrip_signal_observed",
            "current_persists",
            "fault_classified",
            "trip_command_observed",
        ],
        "forbid": ["bus_diff_operated"],
        "primary_hypothesis": "BREAKER_FAILURE",
        "fallback_hypothesis": "INTERTRIP_OPERATION",
        "fallback_when_missing": ["current_persists"],
    },
    ("System", "Cascade trip caused by protection coordination"): {
        "priority": 94,
        "prefer_primary": True,
        "required_any": ["cascade_coordination_failure", "backup_cascade_clearing"],
        "supporting_any": ["protection_operated", "fault_classified", "cascade_upstream_clearance"],
        "forbid": ["bus_diff_operated"],
        "primary_hypothesis": "BREAKER_FAILURE",
        "fallback_hypothesis": "PROTECTION_SETTING_ERROR",
    },
    ("System", "Bus/incomer trip caused by downstream feeder breaker failure"): {
        "priority": 97,
        "prefer_primary": True,
        "required_any": ["cascade_lbb_detected", "downstream_bf_upstream_trip"],
        "supporting_any": ["bf_logic_satisfied", "intertrip_receive_observed", "fault_classified"],
        "forbid": ["bus_diff_operated"],
        "primary_hypothesis": "BREAKER_FAILURE",
    },
    ("System", "Multiple-breaker cascade without bus fault"): {
        "priority": 96,
        "prefer_primary": True,
        "required_any": ["cascade_lbb_detected", "multi_breaker_cascade"],
        "supporting_any": ["bf_logic_satisfied", "intertrip_signal_observed"],
        "forbid": ["bus_diff_operated"],
        "primary_hypothesis": "BREAKER_FAILURE",
    },
    ("System", "Successful backup clearing after primary breaker failure"): {
        "priority": 95,
        "prefer_primary": True,
        "required_any": ["cascade_lbb_detected", "bf_logic_satisfied"],
        "supporting_any": ["cascade_upstream_clearance", "intertrip_receive_observed", "successful_clearing"],
        "forbid": ["bus_diff_operated"],
        "primary_hypothesis": "BREAKER_FAILURE",
    },
    ("Instrumentation", "VT failure / voltage measurement loss"): {
        "priority": 82,
        "prefer_primary": True,
        "required_any": ["voltage_channel_anomaly", "vt_fail_indicated"],
        "primary_hypothesis": "VT_CVT_ABNORMALITY",
    },
    ("Instrumentation", "CT saturation / current measurement distortion"): {
        "priority": 83,
        "prefer_primary": True,
        "required_any": ["ct_saturation_suspected", "waveform_distortion"],
        "supporting_any": ["harmonic_evidence"],
        "primary_hypothesis": "CT_SATURATION",
    },
    ("Instrumentation", "CT polarity/ratio/channel mismatch"): {
        "priority": 81,
        "prefer_primary": True,
        "required_any": ["ct_channel_mismatch", "ct_polarity_error"],
        "primary_hypothesis": "CT_SATURATION",
        "fallback_hypothesis": "RELAY_CONFIGURATION_ERROR",
    },
    ("Control", "Protection logic/control-system malfunction"): {
        "priority": 72,
        "prefer_primary": True,
        "required_any": ["control_logic_maloperation", "logic_malfunction_indicated"],
        "supporting_any": ["mismatch_documented", "configuration_verified"],
        "primary_hypothesis": "RELAY_CONFIGURATION_ERROR",
        "fallback_hypothesis": "RELAY_MISOPERATION",
    },
    ("Protection", "Protection maloperation / unexplained trip"): {
        "priority": 70,
        "prefer_primary": True,
        "required": ["trip_observed", "electrical_no_fault"],
        "supporting_any": ["settings_verified"],
        "primary_hypothesis": "RELAY_MISOPERATION",
    },
}


def _yaml_list(key: str, items: list[str] | None, indent: int = 4) -> list[str]:
    if not items:
        return []
    sp = " " * indent
    lines = [f"{sp}{key}:"]
    for it in items:
        lines.append(f"{sp}  - {it}")
    return lines


def main() -> None:
    data = json.loads(EXPORT.read_text(encoding="utf-8"))
    scenarios = data["scenarios"]
    assert len(scenarios) == 54, len(scenarios)

    lines: list[str] = []
    lines.append("# Versioned RCA scenario matrix (FULL Excel pack — 54 scenarios).")
    lines.append("# Source: Complete_Generalized_Protection_RCA_Matrix_L1_L2_L3_Fallback_LBB.xlsx")
    lines.append("# Generated by backend/scripts/generate_full_matrix_yaml.py — do not hand-trim rows.")
    lines.append("# Consumed by rca.matrix.match_matrix; does NOT replace hypotheses.yaml IDs.")
    lines.append('version: "1.1.0"')
    lines.append('source: "Complete_Generalized_Protection_RCA_Matrix_L1_L2_L3_Fallback_LBB.xlsx"')
    lines.append("source_scenario_count: 54")
    lines.append("engine: HypothesisEngine")
    lines.append("")
    lines.append("layers:")
    lines.append('  L1: "Relay digitals / protection operations (ANSI assert)"')
    lines.append('  L2: "SOE / event report timeline merge"')
    lines.append('  L3: "COMTRADE DR — waveforms, electrical, fault features"')
    lines.append("")
    lines.append("fallback_methodology:")
    for row in data.get("fallback_methodology") or []:
        lvl = str(row.get("level") or "").replace('"', "'")
        rule = str(row.get("rule") or "").replace('"', "'")
        lines.append(f'  - level: "{lvl}"')
        lines.append(f'    rule: "{rule}"')
    lines.append("")
    lines.append("rca_taxonomy:")
    for row in data.get("rca_taxonomy") or []:
        c = str(row.get("classification") or "").replace('"', "'")
        m = str(row.get("meaning") or "").replace('"', "'")
        lines.append(f'  - classification: "{c}"')
        lines.append(f'    meaning: "{m}"')
    lines.append("")
    lines.append("# IEEE / Excel LBB Cascade Logic (10 steps)")
    lines.append("lbb_steps:")
    # Keep executable evidence mapping aligned with Excel meanings
    lbb_exec = [
        (1, "Credible primary fault signature", ["fault_classified", "fault_classified_strong", "current_increase_observed"]),
        (2, "Primary protection START/OPERATE", ["protection_operated", "trip_observed"]),
        (3, "Trip command to local breaker", ["trip_command_observed", "trip_observed"]),
        (4, "Local breaker status / open confirmation", ["breaker_open_confirmed", "successful_clearing"]),
        (5, "Current persistence / failed clear", ["current_persists", "bf_logic_satisfied"]),
        (6, "50BF / LBB element operates", ["bf_logic_satisfied", "cascade_lbb_detected"]),
        (7, "Intertrip / transfer-trip SEND", ["intertrip_send_observed", "intertrip_signal_observed"]),
        (8, "Upstream / backup receives intertrip", ["intertrip_receive_observed", "cascade_upstream_clearance"]),
        (9, "Backup trip / clearance", ["protection_operated", "cascade_upstream_clearance", "successful_clearing"]),
        (10, "Bus-zone fault excluded without 87B", None),
    ]
    for sid, label, any_of in lbb_exec:
        lines.append(f"  - id: {sid}")
        lines.append(f'    label: "{label}"')
        if sid == 10:
            lines.append("    forbid: [bus_diff_operated]")
            lines.append("    require_absent_for_pass: true")
            lines.append('    note: "Pass when bus_diff_operated is absent (Excel: not automatically a bus fault)"')
        else:
            lines.append("    any_of:")
            for t in any_of or []:
                lines.append(f"      - {t}")
    lines.append("")
    lines.append("scenarios:")

    # Aliases for backward-compatible IDs used by existing tests
    aliases = {
        ("System", "Local Breaker Backup / LBB cascade clearing"): "SC_LBB_CASCADE_COMPOUND",
        ("Feeder/Line", "Switch onto fault"): "SC_SWITCH_ONTO_FAULT",
        ("Feeder/Line", "Phase-earth in-zone fault"): "SC_FEEDER_INZONE",
        ("Feeder/Line", "Three-phase in-zone fault"): "SC_LINE_ZONE_FAULT",
        ("Transformer", "Internal phase fault"): "SC_XFMR_INTERNAL_THROUGH_EXCLUDED",
        ("Transformer", "Energization inrush"): "SC_INRUSH_ENERGIZATION_FALLBACK",
        ("Busbar", "Internal bus fault"): "SC_BUS_ZONE_REQUIRES_87B",
    }

    missing_map = []
    for sc in scenarios:
        key = (sc["asset"], sc["scenario"])
        cfg = MAP.get(key)
        if not cfg:
            missing_map.append(key)
            continue
        sid = aliases.get(key) or _slug(sc["asset"], sc["scenario"])
        title = sc["scenario"].replace('"', "'")
        compound = sc["final_class"].replace('"', "'")
        fb = sc["fallback"].replace('"', "'").replace("\n", " ")
        if len(fb) > 220:
            fb = fb[:217] + "..."
        lines.append(f"  - id: {sid}")
        lines.append(f'    title: "{title}"')
        lines.append(f'    asset: "{sc["asset"]}"')
        lines.append(f"    excel_row: {sc['row']}")
        lines.append(f"    priority: {cfg['priority']}")
        lines.append(f"    prefer_primary: {str(bool(cfg.get('prefer_primary', True))).lower()}")
        lines.append("    levels: [L1, L2, L3]")
        lines.extend(_yaml_list("required", cfg.get("required")))
        lines.extend(_yaml_list("required_any", cfg.get("required_any")))
        lines.extend(_yaml_list("supporting_any", cfg.get("supporting_any")))
        lines.extend(_yaml_list("forbid", cfg.get("forbid")))
        lines.append(f"    primary_hypothesis: {cfg['primary_hypothesis']}")
        lines.append(f'    compound_class: "{compound}"')
        if cfg.get("fallback_hypothesis"):
            lines.append(f"    fallback_hypothesis: {cfg['fallback_hypothesis']}")
        if cfg.get("fallback_when_missing"):
            lines.extend(_yaml_list("fallback_when_missing", cfg["fallback_when_missing"]))
        note = cfg.get("fallback_note") or fb
        if note:
            lines.append(f'    fallback_note: "{note}"')
        lines.append("    traces:")
        lines.append(f'      - "Matrix {sid} matched (Excel row {sc["row"]})"')
        lines.append(f'      - "Final class: {compound}"')
        lines.append("")

    if missing_map:
        raise SystemExit(f"Unmapped scenarios: {missing_map}")

    lines.append("guardrails:")
    lines.append("  - id: GR_NO_BUS_WITHOUT_87B")
    lines.append('    description: "Cascade / feeder events must not surface BUS_ZONE_FAULT without bus_diff_operated"')
    lines.append("    when_any: [cascade_lbb_detected, fault_classified, protection_operated]")
    lines.append("    unless: [bus_diff_operated]")
    lines.append("    demote_hypothesis: BUS_ZONE_FAULT")
    lines.append("    demote_to: UNLIKELY")
    lines.append('    reason: "No 87B / bus-diff evidence — bus fault excluded (matrix guardrail)"')
    lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} with {len(scenarios)} scenarios")


if __name__ == "__main__":
    main()
