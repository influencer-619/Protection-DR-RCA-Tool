"""Hypothesis-based RCA engine (deterministic, evidence-gated)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from app.core.enums import HypothesisStatus
from common.rules_path import load_yaml, resolve_rules_root
from consistency.engine import ConsistencyResult
from fault_analysis import FaultClassificationResult, motor_start_context
from protection.models import ProtectionAssessment

_SOTF_NAME_RE = re.compile(
    r"\bSOTF\b|SWITCH[\s_\-]?ON[\s_\-]?TO[\s_\-]?FAULT|"
    r"CLOSE[\s_\-]?ON[\s_\-]?TO[\s_\-]?FAULT|SWITCH[\s_\-]?ONTO|"
    r"ENERGI[sz]E[\s_\-]?ON[\s_\-]?FAULT",
    re.I,
)


DEFAULT_WEIGHTS = {
    "deterministic": 0.50,
    "consistency": 0.20,
    "electrical": 0.15,
    "ml": 0.10,
    "similarity": 0.05,
}

# Hypotheses that are electrical/plant fault explanations (not relay blame)
FAULT_SIDE_HYPOTHESES = frozenset(
    {
        "EXTERNAL_LINE_FAULT",  # line / distance / 87L
        "INTERNAL_FEEDER_FAULT",  # feeder OC / EF
        "CABLE_FAULT",
        "TRANSFORMER_INTERNAL_FAULT",  # 87T / 87RGF
        "BUS_ZONE_FAULT",  # 87B
        "GENERATOR_INTERNAL_FAULT",  # 87G
        "LIGHTNING",
        "VEGETATION",
        "INSULATION_FLASHOVER",
        "EXTERNAL_GRID_DISTURBANCE",  # 27/59/81-leaning
        "SWITCHING_TRANSIENT",
        "SWITCH_ONTO_FAULT",  # close / energize into a shunt fault (SOTF)
        "MOTOR_START",
        "MOTOR_LOCKED_ROTOR",
        "MOTOR_LOAD_JAM",
        "HIGH_IMPEDANCE_FAULT",
        "INTERMITTENT_EARTH_FAULT",
        "TEMPORARY_FAULT_RECLOSE",
        "PERSISTENT_FAULT_RECLOSE",
        "OVEREXCITATION",
        "THERMAL_OVERLOAD",
        "PHASE_LOSS",
        "NEGATIVE_SEQUENCE",
        "LOSS_OF_EXCITATION",
        "FREQUENCY_EVENT",
        "OUT_OF_STEP",
        "ACCIDENTAL_ENERGIZATION",
        "CAPACITOR_BANK_FAULT",
        "OVERVOLTAGE",
    }
)

# Zone primary hypotheses (mutually exclusive by operated scheme)
ZONE_PRIMARY_HYPOTHESES = frozenset(
    {
        "EXTERNAL_LINE_FAULT",
        "INTERNAL_FEEDER_FAULT",
        "TRANSFORMER_INTERNAL_FAULT",
        "BUS_ZONE_FAULT",
        "GENERATOR_INTERNAL_FAULT",
    }
)

# External cause hyps — only meaningful for overhead/cable circuits (not 87T/87B/87G zones)
LINE_FEEDER_CAUSE_HYPOTHESES = frozenset(
    {
        "LIGHTNING",
        "VEGETATION",
        "INSULATION_FLASHOVER",
        "CABLE_FAULT",
    }
)

# Evidence tokens that specifically support each cause (without these → INCONCLUSIVE, not POSSIBLE)
CAUSE_EVIDENCE_TOKENS: dict[str, frozenset[str]] = {
    "LIGHTNING": frozenset({"lightning_evidence"}),
    "VEGETATION": frozenset({"field_report_vegetation"}),
    "INSULATION_FLASHOVER": frozenset({"insulation_evidence"}),
    "CABLE_FAULT": frozenset({"cable_asset_confirmed"}),
}

# ANSI / IEEE function families for scheme-aware RCA scoring
_FAMILY_DISTANCE = frozenset({"21", "21G", "21P"})
_FAMILY_OVERCURRENT = frozenset({"50", "51", "50P", "51P"})
_FAMILY_EARTH_FAULT = frozenset({"50N", "51N", "67N", "87RGF"})
_FAMILY_MOTOR = frozenset({"46", "48", "49"})
_FAMILY_LINE_DIFF = frozenset({"87L"})
_FAMILY_XFMR_DIFF = frozenset({"87T", "87RGF"})
_FAMILY_BUS_DIFF = frozenset({"87B"})
_FAMILY_GEN_DIFF = frozenset({"87G"})
_FAMILY_BREAKER_FAILURE = frozenset({"50BF"})
_FAMILY_DIRECTIONAL = frozenset({"67", "67N", "67P"})
_FAMILY_VOLTAGE = frozenset({"27", "59"})
_FAMILY_FREQUENCY = frozenset({"81U", "81O", "81R"})
_FAMILY_POWER_SWING = frozenset({"68", "78"})
_FAMILY_RECLOSE_LOCKOUT = frozenset({"79", "86"})
_FAMILY_SYNC = frozenset({"25"})
_FAMILY_POWER = frozenset({"32R", "46"})


def _element_code(assessment: ProtectionAssessment) -> str:
    return str(getattr(assessment, "element", "") or "").upper().strip()


def _assessment_has_digital_evidence(assessment: ProtectionAssessment) -> bool:
    from protection.operate_evidence import assessment_has_operate_evidence

    evid = list(getattr(assessment, "evidence_ids", None) or [])
    meta = getattr(assessment, "metadata", None)
    bag: dict = {"evidence_ids": evid}
    if isinstance(meta, dict):
        bag["metadata"] = meta
    return assessment_has_operate_evidence(bag)


def _assessment_operated(assessment: ProtectionAssessment) -> bool:
    """True when the element showed digital activity (pickup and/or trip)."""
    if not _assessment_has_digital_evidence(assessment):
        return False
    act = str(assessment.actual_operation or "").upper()
    return (
        assessment.pickup is True
        or assessment.trip is True
        or act in ("OPERATED", "PICKED_UP", "TRIPPED")
    )


def _assessment_tripped(assessment: ProtectionAssessment) -> bool:
    """True only when a trip assert is evidenced (not pickup-only)."""
    if not _assessment_has_digital_evidence(assessment):
        return False
    act = str(assessment.actual_operation or "").upper()
    if assessment.trip is True or act == "TRIPPED":
        return True
    # Explicit trip=False → never treat as trip (pickup-only assessments)
    if assessment.trip is False:
        return False
    # OPERATED + pickup without trip flag → pickup framing, not trip
    if act == "OPERATED" and assessment.pickup is True:
        return False
    if act == "OPERATED":
        return True
    return False


def _protection_assert_token(*, any_pickup: bool, any_trip: bool) -> Optional[str]:
    """Evidence token that states pickup / trip / pickup with trip explicitly."""
    if any_pickup and any_trip:
        return "protection_pickup_with_trip"
    if any_pickup:
        return "protection_pickup_asserted"
    if any_trip:
        return "protection_trip_asserted"
    return None


def _sotf_name_hit(names: list[Any] | tuple[Any, ...] | None) -> bool:
    """True when a digital / channel name indicates switch-onto-fault logic."""
    for n in names or []:
        if n is None:
            continue
        if _SOTF_NAME_RE.search(str(n)):
            return True
    return False


def _sotf_from_assessments(assessments: list[ProtectionAssessment]) -> bool:
    """True when an assessment evidence id / element label looks like SOTF."""
    for a in assessments or []:
        if _SOTF_NAME_RE.search(str(getattr(a, "element", "") or "")):
            return True
        for eid in getattr(a, "evidence_ids", None) or []:
            if _SOTF_NAME_RE.search(str(eid)):
                return True
        meta = getattr(a, "metadata", None)
        if isinstance(meta, dict):
            for key in ("channel", "channel_name", "digital", "source"):
                if _SOTF_NAME_RE.search(str(meta.get(key) or "")):
                    return True
    return False


def _protection_assert_phrase(bag: set[str]) -> Optional[str]:
    """Human phrase for narrative: pickup, trip, or pickup with trip."""
    if "protection_pickup_with_trip" in bag:
        return "protection pickup with trip"
    if "protection_pickup_asserted" in bag:
        return "protection pickup asserted"
    if "protection_trip_asserted" in bag or "protection_operated" in bag:
        return "protection trip asserted"
    if "protection_responded" in bag:
        return "protection response asserted"
    return None


def _element_assert_phrase(
    bag: set[str],
    *,
    operated_tok: str,
    pickup_tok: str,
    label: str,
) -> Optional[str]:
    """Say trip vs pickup clearly — never 'operated' for pickup-only.

    Prefer ``_family_assert_phrase`` when assessments are available so the
    narrative lists exact ANSI codes (50N, 51N) instead of a family range.
    """
    if operated_tok in bag:
        if pickup_tok in bag or "protection_pickup_with_trip" in bag:
            return f"{label} pickup with trip"
        return f"{label} trip asserted"
    if pickup_tok in bag:
        return f"{label} pickup asserted (no trip digital)"
    return None


def _format_ansi_codes(codes: list[str]) -> str:
    """``50P (Phase instantaneous overcurrent), 50BF (Breaker failure)``."""
    try:
        from protection.ansi_names import format_ansi

        return ", ".join(format_ansi(c) for c in codes)
    except Exception:  # noqa: BLE001
        return ", ".join(codes)


def _all_asserted_ansi_phrase(assessments: list[ProtectionAssessment]) -> Optional[str]:
    """All digitally evidenced ANSI asserts with technical names."""
    tripped: list[str] = []
    pickup_only: list[str] = []
    seen_t: set[str] = set()
    seen_p: set[str] = set()
    for a in assessments:
        code = _element_code(a)
        if not code:
            continue
        if not _assessment_has_digital_evidence(a):
            continue
        if _assessment_tripped(a):
            if code not in seen_t:
                seen_t.add(code)
                tripped.append(code)
        elif a.pickup is True or (
            _assessment_operated(a) and not _assessment_tripped(a)
        ):
            if code not in seen_p and code not in seen_t:
                seen_p.add(code)
                pickup_only.append(code)
    parts: list[str] = []
    if tripped:
        parts.append(f"{_format_ansi_codes(tripped)} trip asserted")
    if pickup_only:
        parts.append(f"{_format_ansi_codes(pickup_only)} pickup only (no trip)")
    return "; ".join(parts) if parts else None


def _step_by_step_evidence_chain(
    bag: set[str],
    assessments: list[ProtectionAssessment],
    fault: FaultClassificationResult,
    consistency: ConsistencyResult,
    *,
    hypothesis_steps: Optional[list[Optional[str]]] = None,
) -> list[str]:
    """Industry-style ordered evidence trail for every RCA hypothesis.

    Always walks: waveforms/electrical → digitals (ANSI) → SOE/timeline markers
    → scheme/cascade context → consistency → hypothesis-specific conclusion steps.
    """
    ft = fault.fault_type if fault.fault_type and fault.fault_type != "UNKNOWN" else None
    steps: list[str] = []

    # 1) Waveforms / electrical
    elec: list[str] = []
    if "fault_classified" in bag or "fault_classified_strong" in bag:
        elec.append(f"fault typed {ft or 'UNKNOWN'} ({fault.status})")
    if "current_increase_observed" in bag:
        elec.append("fault current increase on waveforms")
    if "current_persists" in bag:
        elec.append("current persisted after trip command")
    if "loop_impedance_available" in bag or "distance_estimate_available" in bag:
        elec.append("impedance / distance estimate available")
    if "waveform_distortion" in bag:
        elec.append("waveform distortion observed")
    if "harmonic_evidence" in bag:
        elec.append("harmonic / inrush signature")
    if "electrical_no_fault" in bag or "dfr_non_fault_event" in bag:
        elec.append("electrical evidence leans non-fault / disturbance")
    if "magnetizing_inrush_possible" in bag:
        elec.append("magnetizing inrush possible")
    if "motor_start_possible" in bag:
        elec.append("motor-start current signature")
    steps.append(
        "1. Waveforms / electrical: " + ("; ".join(elec) if elec else "reviewed (no strong shunt-fault flags)")
    )

    # 2) Digitals / ANSI operates
    ansi = _all_asserted_ansi_phrase(assessments)
    dig: list[str] = []
    if ansi:
        dig.append(ansi)
    else:
        ph = _protection_assert_phrase(bag)
        if ph:
            dig.append(ph)
        for tok, label in (
            ("overcurrent_element_operated", "overcurrent (50/51) trip"),
            ("earth_fault_element_operated", "earth-fault (50N/51N/67N) trip"),
            ("distance_element_operated", "distance (21) trip"),
            ("line_diff_operated", "line differential (87L) trip"),
            ("transformer_diff_operated", "transformer differential (87T) trip"),
            ("bus_diff_operated", "bus differential (87B) trip"),
            ("generator_diff_operated", "generator differential (87G) trip"),
            ("bf_logic_satisfied", "breaker failure (50BF) logic"),
            ("sotf_element_asserted", "SOTF element"),
        ):
            if tok in bag and not any(tok.split("_")[0] in (d or "") for d in dig):
                dig.append(label)
    steps.append(
        "2. Digitals / protection asserts: "
        + ("; ".join(dig) if dig else "no clear protection digital trip/pickup mapped")
    )

    # 3) SOE / intertrip / timeline context
    soe: list[str] = []
    if "intertrip_receive_observed" in bag:
        soe.append("intertrip / transfer-trip RECEIVE observed (backup clearance role)")
    elif "intertrip_send_observed" in bag:
        soe.append("intertrip / transfer-trip SEND observed (LBB transfer)")
    elif "intertrip_signal_observed" in bag:
        soe.append("intertrip / transfer-trip digital observed")
    if "cascade_lbb_detected" in bag:
        soe.append("LBB / multi-bay cascade pattern detected")
    if "cascade_upstream_clearance" in bag:
        soe.append("upstream / backup clearance (cascade consequence)")
    if "trip_command_observed" in bag:
        soe.append("trip command observed on timeline")
    if "breaker_close_observed" in bag:
        soe.append("breaker close before trip (close-into-fault context)")
    if "autoreclose_issued" in bag:
        soe.append("autoreclose (79) issued")
    if "comm_channel_evidence" in bag:
        soe.append("COMM / pilot channel evidence")
    if "switching_event_correlated" in bag:
        soe.append("switching event correlated")
    steps.append(
        "3. SOE / sequence markers: "
        + ("; ".join(soe) if soe else "timeline reviewed (no intertrip/cascade markers)")
    )

    # 4) Consistency / settings
    steps.append(f"4. Settings vs observed: {consistency.summary_status}")

    # 5+) Hypothesis-specific conclusion steps
    for i, raw in enumerate(hypothesis_steps or []):
        if not raw:
            continue
        text = str(raw).strip()
        if not text:
            continue
        # Avoid duplicating numbered universal steps already added
        if text.startswith(("1.", "2.", "3.", "4.")):
            steps.append(text)
        else:
            steps.append(f"{5 + i}. {text}")

    return steps


def _merge_causal_chain(
    bag: set[str],
    assessments: list[ProtectionAssessment],
    fault: FaultClassificationResult,
    consistency: ConsistencyResult,
    *,
    hypothesis_steps: Optional[list[Optional[str]]] = None,
    legacy_fallback: Optional[list[str]] = None,
) -> list[str]:
    chain = _step_by_step_evidence_chain(
        bag,
        assessments,
        fault,
        consistency,
        hypothesis_steps=hypothesis_steps,
    )
    if len(chain) <= 4 and legacy_fallback:
        # Keep any unique legacy tokens as trailing notes
        for item in legacy_fallback:
            s = str(item or "").strip()
            if s and s not in chain:
                chain.append(s)
    return chain


def _family_assert_phrase(
    assessments: list[ProtectionAssessment],
    family: frozenset[str],
) -> Optional[str]:
    """Exact asserted codes — e.g. ``50N (…), 51N (…) pickup with trip`` (never invent 67N)."""
    tripped: list[str] = []
    pickup_only: list[str] = []
    seen_t: set[str] = set()
    seen_p: set[str] = set()
    for a in assessments:
        code = _element_code(a)
        if not code or code not in family:
            continue
        if not _assessment_has_digital_evidence(a):
            continue
        if _assessment_tripped(a):
            if code not in seen_t:
                seen_t.add(code)
                tripped.append(code)
        elif a.pickup is True or (
            _assessment_operated(a) and not _assessment_tripped(a)
        ):
            if code not in seen_p and code not in seen_t:
                seen_p.add(code)
                pickup_only.append(code)
    parts: list[str] = []
    if tripped:
        parts.append(f"{_format_ansi_codes(tripped)} pickup with trip")
    if pickup_only:
        parts.append(
            f"{_format_ansi_codes(pickup_only)} pickup asserted (no trip digital)"
        )
    return "; ".join(parts) if parts else None


def _diff_dict_from_assessment(
    assessment: ProtectionAssessment,
    electrical_flags: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Prefer element metadata; else event multi-end / compute from winding currents."""
    meta = assessment.metadata if isinstance(assessment.metadata, dict) else {}
    diff = meta.get("differential")
    if isinstance(diff, dict) and diff.get("status"):
        return diff
    flags = electrical_flags if isinstance(electrical_flags, dict) else {}
    if isinstance(flags.get("diff_87"), dict):
        return flags["diff_87"]
    from protection.physics import _c, differential_operate_restraint

    return differential_operate_restraint(
        i_w1=_c(flags.get("i_w1")),
        i_w2=_c(flags.get("i_w2")),
        i_local=_c(flags.get("i_local")),
        i_remote=_c(flags.get("i_remote")),
        slope=float(flags.get("diff_slope") or 0.3),
        pickup_a=float(flags.get("diff_pickup_a") or 0.2),
    )


def _phase_ct_sat_indicated(flags: dict[str, Any]) -> bool:
    """True only when phase-CT saturation is indicated (ignore residual/IN-only)."""
    if bool(flags.get("waveform_distortion")) and bool(flags.get("harmonic_evidence")):
        return True
    det = flags.get("detectors") if isinstance(flags.get("detectors"), dict) else {}
    ct = det.get("ct_saturation") if isinstance(det, dict) else {}
    if not isinstance(ct, dict) or str(ct.get("status") or "").upper() != "POSSIBLE":
        return False
    suspects = ct.get("suspects") if isinstance(ct.get("suspects"), list) else []
    for s in suspects:
        if not isinstance(s, dict):
            continue
        role = str(s.get("role") or "").upper().strip()
        ch = str(s.get("channel") or "").upper().strip()
        if role in ("IA", "IB", "IC", "I"):
            return True
        # Channel names like IA, IB_PRI — not IN / IN_PRI
        base = ch.split("_")[0]
        if base in ("IA", "IB", "IC"):
            return True
    return False


def _through_fault_excluded_from_xfmr(
    assessments: list[ProtectionAssessment],
    electrical_flags: Optional[dict[str, Any]] = None,
) -> bool:
    """
    Assert through-fault exclusion when Id/Ir supports an internal 87T/87RGF operate,
    or (weaker) when Id/Ir is unavailable but operate is consistent without phase CT-sat / inrush.
    """
    flags = electrical_flags if isinstance(electrical_flags, dict) else {}
    if flags.get("through_fault_excluded") is True:
        return True

    ct_sat_suspect = _phase_ct_sat_indicated(flags)

    soft_ok = False
    for a in assessments:
        code = _element_code(a)
        if code not in _FAMILY_XFMR_DIFF:
            continue
        if not _assessment_operated(a):
            continue

        meta = a.metadata if isinstance(a.metadata, dict) else {}
        inrush = meta.get("inrush") if isinstance(meta.get("inrush"), dict) else {}
        if not inrush:
            det = flags.get("detectors") if isinstance(flags.get("detectors"), dict) else {}
            inrush = det.get("magnetizing_inrush") if isinstance(det, dict) else {}
        if isinstance(inrush, dict) and str(inrush.get("status") or "").upper() == "POSSIBLE":
            continue

        diff = _diff_dict_from_assessment(a, flags)
        status = str(diff.get("status") or "").upper()

        if status == "OK" and diff.get("operate_expected") is True:
            operate = diff.get("operate_a")
            restraint = diff.get("restraint_a")
            threshold = diff.get("threshold_a")
            slope = float(diff.get("slope") or 0.3)
            try:
                op = float(operate) if operate is not None else None
                ir = float(restraint) if restraint is not None else None
                thr = float(threshold) if threshold is not None else None
            except (TypeError, ValueError):
                continue
            if op is None or ir is None:
                continue
            if thr is None:
                pickup = float(diff.get("pickup_a") or 0.2)
                thr = pickup + slope * ir
            if op < thr * 1.08:
                continue
            id_ir = op / max(ir, 1e-9)
            if id_ir < max(0.45, slope + 0.15):
                continue
            if ct_sat_suspect and id_ir < 1.0:
                continue
            return True

        # Soft path: no winding phasors for Id/Ir — allow exclusion when operate
        # is settings-consistent and phase CT-sat / inrush are not indicated.
        if status in ("NOT_CALCULABLE", "NOT_AVAILABLE", ""):
            if ct_sat_suspect:
                continue
            cons = str(a.consistency or "").upper()
            expected = str(a.expected_operation or "").upper()
            if cons == "CONSISTENT" or expected == "OPERATE" or a.trip is True:
                soft_ok = True

    return soft_ok


def _active_protection_zones(bag: set[str]) -> frozenset[str]:
    """Infer which protection zones are active from operated-element evidence tokens."""
    zones: set[str] = set()
    if (
        "distance_element_operated" in bag
        or "distance_element_picked_up" in bag
        or "line_diff_operated" in bag
    ):
        zones.add("line")
    if (
        "overcurrent_element_operated" in bag
        or "earth_fault_element_operated" in bag
        or "overcurrent_element_picked_up" in bag
        or "earth_fault_element_picked_up" in bag
    ) and "transformer_diff_operated" not in bag and "bus_diff_operated" not in bag and "generator_diff_operated" not in bag and "line_diff_operated" not in bag:
        # OC/EF trip or pickup → feeder/local; 87RGF also sets earth_fault but usually with xfmr
        if "distance_element_operated" not in bag and "distance_element_picked_up" not in bag:
            zones.add("feeder")
        else:
            zones.add("line")
    if "transformer_diff_operated" in bag:
        zones.add("xfmr")
    if "bus_diff_operated" in bag:
        zones.add("bus")
    if "generator_diff_operated" in bag:
        zones.add("gen")
    if "bf_logic_satisfied" in bag:
        zones.add("bf")
    if "voltage_element_operated" in bag or "frequency_element_operated" in bag:
        if not zones:
            zones.add("grid")
    return frozenset(zones)


def _hypothesis_scheme_fit(hid: str, bag: set[str]) -> str:
    """
    Map hypothesis to operated scheme (industry practice).

    Returns:
      match       — zone/cause fits the operated protection
      pending     — cause could fit the zone but lacks specific field evidence
      mismatch    — wrong zone (e.g. vegetation on 87T, bus on 51-only)
      open        — no strong scheme signal yet; do not force UNLIKELY
    """
    zones = _active_protection_zones(bag)
    unit_diff = bool(zones & {"xfmr", "bus", "gen"})
    line_like = bool(zones & {"line", "feeder"}) or (
        not zones and ("scheme_distance_present" in bag or "scheme_overcurrent_present" in bag)
    )

    if hid == "EXTERNAL_LINE_FAULT":
        if "distance_element_operated" in bag or "line_diff_operated" in bag:
            return "match"
        if unit_diff:
            return "mismatch"
        if "overcurrent_element_operated" in bag or "earth_fault_element_operated" in bag:
            return "mismatch"
        return "open" if not zones else "mismatch"

    if hid == "INTERNAL_FEEDER_FAULT":
        if "feeder" in zones:
            return "match"
        if unit_diff or "distance_element_operated" in bag or "line_diff_operated" in bag:
            return "mismatch"
        return "open" if not zones else "mismatch"

    if hid == "TRANSFORMER_INTERNAL_FAULT":
        if "xfmr" in zones:
            return "match"
        if zones:
            return "mismatch"
        return "open"

    if hid == "BUS_ZONE_FAULT":
        if "bus" in zones:
            return "match"
        if zones:
            return "mismatch"
        return "open"

    if hid == "GENERATOR_INTERNAL_FAULT":
        if "gen" in zones:
            return "match"
        if zones:
            return "mismatch"
        return "open"

    if hid in LINE_FEEDER_CAUSE_HYPOTHESES:
        # Lightning / vegetation / flashover / cable — overhead or UG circuit causes
        # Not primary explanations for unit-differential zone trips (87T/87B/87G).
        if unit_diff and not line_like:
            return "mismatch"
        if line_like or not zones:
            needed = CAUSE_EVIDENCE_TOKENS.get(hid, frozenset())
            if needed and bag & needed:
                return "match"
            return "pending"
        return "mismatch"

    if hid == "CT_SATURATION":
        # Industry: CT sat is a leading false-trip explanation on diffs during external faults
        if unit_diff or "line_diff_operated" in bag:
            if "waveform_distortion" in bag or "harmonic_evidence" in bag:
                return "match"
            return "pending"
        if line_like:
            return "pending"
        return "open"

    if hid == "BREAKER_FAILURE":
        if "bf" in zones or "bf_logic_satisfied" in bag:
            return "match"
        if zones and "bf" not in zones:
            return "mismatch"
        return "open"

    if hid == "EXTERNAL_GRID_DISTURBANCE":
        if "grid" in zones:
            return "match"
        if unit_diff or "distance_element_operated" in bag:
            return "mismatch"
        return "pending" if zones else "open"

    if hid == "COMMUNICATION_FAILURE":
        if "scheme_pilot" in bag or "scheme_profile_pilot_pott" in bag or "scheme_id_pilot_pott" in bag:
            if "comm_channel_evidence" in bag:
                return "match"
            return "pending"
        if "line_diff_operated" in bag:
            return "pending"
        return "open"

    if hid == "INTERTRIP_OPERATION":
        if "intertrip_signal_observed" in bag:
            return "match"
        if "scheme_pilot" in bag or line_like:
            return "pending"
        return "open"

    if hid == "SWITCHING_TRANSIENT":
        # Trip + classified fault → prefer SWITCH_ONTO_FAULT / zone hyps
        if "fault_classified" in bag and "protection_operated" in bag:
            return "mismatch"
        if "switching_event_correlated" in bag:
            return "match"
        return "pending" if zones else "open"

    if hid == "SWITCH_ONTO_FAULT":
        if "cascade_lbb_detected" in bag or (
            "bf_logic_satisfied" in bag and "sotf_element_asserted" not in bag
        ):
            return "mismatch"
        if "switch_onto_fault_possible" in bag or "sotf_element_asserted" in bag:
            return "match"
        if (
            "fault_classified" in bag
            and "protection_operated" in bag
            and "breaker_close_observed" in bag
        ):
            return "pending"
        return "open"

    if hid == "MOTOR_START":
        if "motor_start_possible" in bag:
            return "match"
        if "motor_protection_present" in bag or "scheme_motor" in bag:
            return "pending"
        return "open"

    return "open"


def _scheme_tokens_from_assessments(assessments: list[ProtectionAssessment]) -> set[str]:
    """Map operated (or consistently assessed) elements to scheme evidence tokens.

    Unit-differential ``*_operated`` tokens require a **trip** assert. Pickup-only
    (common on magnetizing inrush / restrained 87) is tracked separately so RCA
    does not treat energization pickup as an internal-fault operate.
    """
    tokens: set[str] = set()
    for a in assessments:
        code = _element_code(a)
        if not code:
            continue
        operated = _assessment_operated(a)
        tripped = _assessment_tripped(a)

        def _mark(
            present: str,
            operated_tok: str,
            scheme: str,
            *,
            require_trip: bool = False,
            pickup_tok: Optional[str] = None,
        ) -> None:
            tokens.add(present)
            if require_trip:
                if tripped:
                    tokens.add(operated_tok)
                    tokens.add(scheme)
                elif operated and pickup_tok:
                    tokens.add(pickup_tok)
                    tokens.add(scheme)
            else:
                if operated:
                    tokens.add(operated_tok)
                    tokens.add(scheme)

        if code in _FAMILY_DISTANCE:
            _mark(
                "scheme_distance_present",
                "distance_element_operated",
                "scheme_distance",
                require_trip=True,
                pickup_tok="distance_element_picked_up",
            )
        if code in _FAMILY_OVERCURRENT:
            _mark(
                "scheme_overcurrent_present",
                "overcurrent_element_operated",
                "scheme_overcurrent",
                require_trip=True,
                pickup_tok="overcurrent_element_picked_up",
            )
        if code in _FAMILY_EARTH_FAULT:
            _mark(
                "scheme_earth_fault_present",
                "earth_fault_element_operated",
                "scheme_earth_fault",
                require_trip=True,
                pickup_tok="earth_fault_element_picked_up",
            )
        if code in _FAMILY_LINE_DIFF:
            _mark(
                "scheme_line_diff_present",
                "line_diff_operated",
                "scheme_line_diff",
                require_trip=True,
            )
            if operated and not tripped:
                tokens.add("line_diff_picked_up")
            if tripped:
                tokens.add("differential_operated")
                tokens.add("scheme_differential")
        if code in _FAMILY_XFMR_DIFF:
            _mark(
                "scheme_xfmr_diff_present",
                "transformer_diff_operated",
                "scheme_xfmr_diff",
                require_trip=True,
            )
            if operated and not tripped:
                tokens.add("transformer_diff_picked_up")
            if tripped:
                tokens.add("differential_operated")
                tokens.add("scheme_differential")
        if code in _FAMILY_BUS_DIFF:
            _mark(
                "scheme_bus_diff_present",
                "bus_diff_operated",
                "scheme_bus_diff",
                require_trip=True,
            )
            if operated and not tripped:
                tokens.add("bus_diff_picked_up")
            if tripped:
                tokens.add("differential_operated")
                tokens.add("scheme_differential")
        if code in _FAMILY_GEN_DIFF:
            _mark(
                "scheme_gen_diff_present",
                "generator_diff_operated",
                "scheme_gen_diff",
                require_trip=True,
            )
            if operated and not tripped:
                tokens.add("generator_diff_picked_up")
            if tripped:
                tokens.add("differential_operated")
                tokens.add("scheme_differential")
        if code in _FAMILY_BREAKER_FAILURE:
            # Digital 50BF operated ≠ local BF proven (needs current_persists / cascade)
            _mark(
                "scheme_breaker_failure_present",
                "bf_element_operated",
                "scheme_breaker_failure",
            )
        if code in _FAMILY_DIRECTIONAL:
            _mark(
                "scheme_directional_present",
                "directional_element_operated",
                "scheme_directional",
                require_trip=True,
                pickup_tok="directional_element_picked_up",
            )
        if code in _FAMILY_VOLTAGE:
            _mark(
                "scheme_voltage_present",
                "voltage_element_operated",
                "scheme_voltage",
                require_trip=True,
                pickup_tok="voltage_element_picked_up",
            )
        if code in _FAMILY_FREQUENCY:
            _mark(
                "scheme_frequency_present",
                "frequency_element_operated",
                "scheme_frequency",
                require_trip=True,
                pickup_tok="frequency_element_picked_up",
            )
        if code in _FAMILY_POWER_SWING:
            _mark("scheme_power_swing_present", "power_swing_element_operated", "scheme_power_swing")
        if code in _FAMILY_RECLOSE_LOCKOUT:
            _mark("scheme_reclose_present", "reclose_or_lockout_operated", "scheme_reclose")
        if code in _FAMILY_SYNC:
            _mark("scheme_sync_present", "sync_element_operated", "scheme_sync")
        if code in _FAMILY_POWER:
            _mark(
                "scheme_power_present",
                "power_unbalance_operated",
                "scheme_power",
                require_trip=True,
                pickup_tok="power_unbalance_picked_up",
            )
        if code in _FAMILY_MOTOR:
            _mark(
                "scheme_motor_present",
                "motor_element_operated",
                "scheme_motor",
                require_trip=True,
                pickup_tok="motor_element_picked_up",
            )
    return tokens


STATUS_RANK = {
    HypothesisStatus.CONFIRMED.value: 5,
    HypothesisStatus.PROBABLE.value: 4,
    HypothesisStatus.POSSIBLE.value: 3,
    HypothesisStatus.INCONCLUSIVE.value: 2,
    HypothesisStatus.UNLIKELY.value: 1,
}


@dataclass
class HypothesisResult:
    hypothesis_id: str
    status: str
    score: float
    confidence: str
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    missing_evidence: list[str] = field(default_factory=list)
    statement: str = ""
    explanation: str = ""
    causal_chain: list[str] = field(default_factory=list)
    recommended_actions: list[str] = field(default_factory=list)
    title: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RCAResult:
    hypotheses: list[HypothesisResult] = field(default_factory=list)
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))
    primary: Optional[HypothesisResult] = None
    limitations: list[str] = field(default_factory=list)
    forced_inconclusive: bool = False
    enrichment: dict[str, Any] = field(default_factory=dict)
    scheme: dict[str, Any] = field(default_factory=dict)
    matrix: dict[str, Any] = field(default_factory=dict)
    # ML-014 — explicit availability; never fabricate ML/similarity confidence
    supporting_scores: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "weights": self.weights,
            "primary": self.primary.to_dict() if self.primary else None,
            "limitations": self.limitations,
            "forced_inconclusive": self.forced_inconclusive,
            "enrichment": self.enrichment,
            "scheme": self.scheme,
            "matrix": self.matrix,
            "supporting_scores": self.supporting_scores,
        }


def _load_rca_rules() -> dict[str, Any]:
    path = resolve_rules_root() / "rca" / "hypotheses.yaml"
    if not path.is_file():
        return {"hypotheses": [], "scoring_weights": DEFAULT_WEIGHTS}
    data = load_yaml(path)
    return data if isinstance(data, dict) else {"hypotheses": [], "scoring_weights": DEFAULT_WEIGHTS}


def _title(hid: str) -> str:
    """Scheme-agnostic display titles (IDs stay stable for persistence)."""
    return {
        "EXTERNAL_LINE_FAULT": "Line / protected circuit fault",
        "INTERNAL_FEEDER_FAULT": "Feeder / local circuit fault",
        "CABLE_FAULT": "Cable fault",
        "TRANSFORMER_INTERNAL_FAULT": "Transformer internal fault",
        "BUS_ZONE_FAULT": "Bus zone fault",
        "GENERATOR_INTERNAL_FAULT": "Generator internal fault",
        "EXTERNAL_GRID_DISTURBANCE": "External grid / system disturbance",
        "SWITCHING_TRANSIENT": "Transformer energization / switching",
        "SWITCH_ONTO_FAULT": "Switch onto fault",
        "MOTOR_START": "Motor start / starting current",
        "RELAY_MISOPERATION": "Relay misoperation",
        "PROTECTION_SETTING_ERROR": "Protection setting error",
        "RELAY_CONFIGURATION_ERROR": "Relay configuration error",
        "BREAKER_FAILURE": "Breaker failure",
        "CT_SATURATION": "CT saturation",
        "VT_CVT_ABNORMALITY": "VT / CVT abnormality",
        "LIGHTNING": "Lightning-induced fault",
        "VEGETATION": "Vegetation / tree contact",
        "INSULATION_FLASHOVER": "Insulation flashover",
        "COMMUNICATION_FAILURE": "Protection communication failure",
        "INTERTRIP_OPERATION": "Intertrip / transfer-trip operation",
        "UNKNOWN": "Cause unknown / inconclusive",
    }.get(hid, hid.replace("_", " ").title())


class HypothesisEngine:
    """Score RCA hypotheses from available evidence; never invent measurements."""

    def __init__(self, weights: Optional[dict[str, float]] = None) -> None:
        rules = _load_rca_rules()
        self.hypothesis_defs = list(rules.get("hypotheses") or [])
        cfg_w = rules.get("scoring_weights") or {}
        self.weights = dict(DEFAULT_WEIGHTS)
        self.weights.update({k: float(v) for k, v in cfg_w.items()})
        if weights:
            self.weights.update(weights)
        s = sum(self.weights.values()) or 1.0
        self.weights = {k: v / s for k, v in self.weights.items()}

    def run(
        self,
        *,
        fault: FaultClassificationResult,
        assessments: list[ProtectionAssessment],
        consistency: ConsistencyResult,
        electrical_flags: Optional[dict[str, Any]] = None,
        ml_available: bool = False,
        ml_supports: Optional[dict[str, float]] = None,
        similarity_available: bool = False,
        similarity_supports: Optional[dict[str, float]] = None,
        extra_evidence: Optional[set[str] | list[str]] = None,
        enrichment_detail: Optional[dict[str, Any]] = None,
        scheme_detail: Optional[dict[str, Any]] = None,
    ) -> RCAResult:
        electrical_flags = dict(electrical_flags or {})
        ml_supports = ml_supports or {}
        similarity_supports = similarity_supports or {}

        # DFR event class from fault classifier (IEEE/PSRC order)
        ec = getattr(fault, "event_class", None) or electrical_flags.get("event_class")
        if not ec:
            ec_feat = (fault.evidence or {}).get("event_classification")
            if isinstance(ec_feat, dict):
                ec = ec_feat.get("event_class")
        _non_fault_ec = str(ec or "") in (
            "ENERGIZATION",
            "MOTOR_START",
            "SWITCHING",
            "DISTURBANCE",
        )
        if ec:
            electrical_flags.setdefault("event_class", str(ec))
            # Only explicit non-fault classes suppress shunt-fault framing.
            # UNKNOWN (no timeline gate) must not set no_fault — CLASSIFIED AG/ABC
            # fixtures and current-only records still carry fault_classified.
            if _non_fault_ec:
                electrical_flags.setdefault("no_fault", True)
                electrical_flags["fault_indicated"] = False
                if str(ec) == "ENERGIZATION":
                    electrical_flags.setdefault("magnetizing_inrush", True)
                elif str(ec) == "MOTOR_START":
                    electrical_flags.setdefault("motor_start", True)
                elif str(ec) == "SWITCHING":
                    electrical_flags.setdefault("switching_correlated", True)

        # Derive flags when shunt type is published (FAULT or UNKNOWN gate)
        _ft = str(getattr(fault, "fault_type", "") or "")
        if (
            not _non_fault_ec
            and fault.status in ("CLASSIFIED", "PROBABLE")
            and _ft not in ("", "UNKNOWN")
        ):
            electrical_flags.setdefault("fault_indicated", True)
            feat = fault.evidence if isinstance(fault.evidence, dict) else {}
            if feat.get("available") and any(
                feat.get(k)
                for k in ("Ia_elevated", "Ib_elevated", "Ic_elevated", "ground")
            ):
                electrical_flags.setdefault("current_increase", True)

        result = RCAResult(weights=dict(self.weights))
        result.supporting_scores = {
            "ml": {
                "available": bool(ml_available),
                "status": "OK" if ml_available else "NOT_AVAILABLE",
                "weight": float(self.weights.get("ml") or 0.0),
                "message": (
                    None
                    if ml_available
                    else "ML RESULT: NOT AVAILABLE — score contribution is zero"
                ),
            },
            "similarity": {
                "available": bool(similarity_available),
                "status": "OK" if similarity_available else "NOT_AVAILABLE",
                "weight": float(self.weights.get("similarity") or 0.0),
                "message": (
                    None
                    if similarity_available
                    else "SIMILARITY RESULT: NOT AVAILABLE — score contribution is zero"
                ),
            },
        }
        # ML/similarity unavailability stays on supporting_scores (API / RCA UI).
        # Do not append to limitations — those banners are for engineering gaps only.
        if enrichment_detail:
            result.enrichment = dict(enrichment_detail)
        if scheme_detail:
            result.scheme = dict(scheme_detail)
        if consistency.rca_must_remain_inconclusive:
            result.forced_inconclusive = True
            result.limitations.append(
                "Critical setting inconsistency — relay-malfunction conclusions remain "
                "INCONCLUSIVE until active configuration is verified. Electrical fault "
                "hypotheses may still be ranked from available COMTRADE evidence."
            )

        evidence_bag = self._collect_evidence(
            fault, assessments, consistency, electrical_flags
        )
        if extra_evidence:
            evidence_bag |= {str(t) for t in extra_evidence if t}

        # Deep ladder: per-channel digitals (L1), chronological SOE (L2),
        # executable L3 fallbacks when dedicated L1 bits are missing.
        from rca.ladder import build_ladder_deep

        ladder_deep = build_ladder_deep(
            bag=evidence_bag,
            timeline=electrical_flags.get("timeline_events"),
            assessments=assessments,
            digital_channel_names=electrical_flags.get("digital_channel_names"),
            electrical_flags=electrical_flags,
            fault=fault,
        )
        evidence_bag |= ladder_deep.tokens
        # Refresh layer presence after ladder tokens merge
        from rca.matrix import layer_tokens_present

        for layer, present in layer_tokens_present(evidence_bag).items():
            if present:
                evidence_bag.add(f"evidence_{layer.lower()}_present")
        result.enrichment = dict(result.enrichment or {})
        result.enrichment["ladder_deep"] = ladder_deep.to_dict()
        if ladder_deep.traces:
            result.enrichment.setdefault("matrix_traces", [])
            # defer merging traces until after matrix match

        for hyp in self.hypothesis_defs:
            hid = str(hyp.get("id", "UNKNOWN"))
            required = list(hyp.get("required_for_confirmed") or [])
            supporting, contradicting, missing = self._evaluate_evidence(
                hid, required, evidence_bag, fault
            )

            scheme_fit = _hypothesis_scheme_fit(hid, evidence_bag)
            if scheme_fit == "mismatch":
                if "scheme_zone_mismatch" not in contradicting:
                    contradicting.append("scheme_zone_mismatch")

            det = self._deterministic_score(hid, evidence_bag, fault)
            cons = self._consistency_score(hid, consistency)
            elec = self._electrical_score(hid, fault, electrical_flags, evidence_bag)

            # Soft penalty when scheme evidence contradicts the hypothesis
            if contradicting:
                det = max(0.0, det - 0.08 * min(len(contradicting), 3))

            # Hard demotion for wrong protection zone (industry: causes must match zone)
            if scheme_fit == "mismatch":
                det = min(det, 0.12)
                elec = min(elec, 0.20)
            elif scheme_fit == "pending" and hid in LINE_FEEDER_CAUSE_HYPOTHESES:
                # No lightning/vegetation/cable field evidence yet → keep low
                det = min(det, 0.22)
                elec = min(elec, 0.35)

            ml_s = float(ml_supports.get(hid, 0.0)) if ml_available else 0.0
            sim_s = (
                float(similarity_supports.get(hid, 0.0)) if similarity_available else 0.0
            )

            score = (
                self.weights["deterministic"] * det
                + self.weights["consistency"] * cons
                + self.weights["electrical"] * elec
                + self.weights["ml"] * ml_s
                + self.weights["similarity"] * sim_s
            )

            # Status gating — CONFIRMED needs full required evidence; PROBABLE uses score
            if result.forced_inconclusive and hid == "RELAY_MISOPERATION":
                status = HypothesisStatus.INCONCLUSIVE.value
                if "active_setting_verification" not in missing:
                    missing = missing + ["active_setting_verification"]
            elif scheme_fit == "mismatch":
                status = HypothesisStatus.UNLIKELY.value
            elif scheme_fit == "pending" and hid in LINE_FEEDER_CAUSE_HYPOTHESES | {
                "CT_SATURATION",
                "VT_CVT_ABNORMALITY",
                "COMMUNICATION_FAILURE",
                "INTERTRIP_OPERATION",
                "SWITCHING_TRANSIENT",
                "SWITCH_ONTO_FAULT",
            }:
                # Cause/instrument hyps without their specific evidence stay INCONCLUSIVE
                status = HypothesisStatus.INCONCLUSIVE.value
            elif required and not missing and det >= 0.8 and cons >= 0.5:
                status = HypothesisStatus.CONFIRMED.value
            elif score >= 0.65 and det >= 0.45:
                # PROBABLE from available data even if CONFIRMED requirements incomplete
                status = HypothesisStatus.PROBABLE.value
            elif score >= 0.35 or (supporting and det >= 0.35):
                status = HypothesisStatus.POSSIBLE.value
            elif score < 0.25 and contradicting:
                status = HypothesisStatus.UNLIKELY.value
            elif supporting:
                status = HypothesisStatus.POSSIBLE.value
            else:
                status = HypothesisStatus.INCONCLUSIVE.value

            if status == HypothesisStatus.CONFIRMED.value and det < 0.5:
                status = HypothesisStatus.PROBABLE.value
                missing.append("deterministic_evidence_insufficient_for_confirmed")

            # Inrush/charging from H2 alone is PROBABLE, not CONFIRMED (needs SOE/ops confirm)
            if (
                hid == "SWITCHING_TRANSIENT"
                and status == HypothesisStatus.CONFIRMED.value
                and "magnetizing_inrush_possible" in evidence_bag
                and "switching_event_correlated" in evidence_bag
                and "power_swing_element_operated" not in evidence_bag
            ):
                # switching_event_correlated was derived from inrush — require field SOE for CONFIRMED
                status = HypothesisStatus.PROBABLE.value
                if "energization_schedule_or_soe" not in missing:
                    missing = missing + ["energization_schedule_or_soe"]

            # Motor start from DR digitals alone — PROBABLE until ops/SOE confirm
            if (
                hid == "MOTOR_START"
                and status == HypothesisStatus.CONFIRMED.value
            ):
                status = HypothesisStatus.PROBABLE.value
                if "motor_start_soe_or_ops_confirm" not in missing:
                    missing = missing + ["motor_start_soe_or_ops_confirm"]

            # SOTF: CONFIRMED only with explicit SOTF digital or breaker-close + trip + fault
            if (
                hid == "SWITCH_ONTO_FAULT"
                and status == HypothesisStatus.CONFIRMED.value
                and "sotf_element_asserted" not in evidence_bag
                and "breaker_close_observed" not in evidence_bag
            ):
                status = HypothesisStatus.PROBABLE.value
                if "breaker_close_or_sotf_digital" not in missing:
                    missing = missing + ["breaker_close_or_sotf_digital"]

            # Never promote mismatch / pending-cause above their gate
            if scheme_fit == "mismatch":
                status = HypothesisStatus.UNLIKELY.value
            elif scheme_fit == "pending" and hid in LINE_FEEDER_CAUSE_HYPOTHESES and status in (
                HypothesisStatus.POSSIBLE.value,
                HypothesisStatus.PROBABLE.value,
                HypothesisStatus.CONFIRMED.value,
            ):
                status = HypothesisStatus.INCONCLUSIVE.value

            conf = (
                "HIGH"
                if status == HypothesisStatus.CONFIRMED.value
                else "MEDIUM"
                if status
                in (HypothesisStatus.PROBABLE.value, HypothesisStatus.POSSIBLE.value)
                else "INCONCLUSIVE"
            )

            narrative = self._narrative(
                hid,
                status,
                fault,
                supporting,
                missing,
                evidence_bag,
                consistency,
                assessments=assessments,
            )
            # Every hypothesis gets the same ordered evidence trail
            # (waveforms → digitals/ANSI → SOE → settings → conclusion).
            hyp_steps = list(narrative.get("causal_chain") or [])
            narrative["causal_chain"] = _merge_causal_chain(
                evidence_bag,
                assessments,
                fault,
                consistency,
                hypothesis_steps=[
                    s
                    for s in hyp_steps
                    if s
                    and not str(s).startswith(
                        ("1. Waveforms", "2. Digitals", "3. SOE", "4. Settings")
                    )
                ],
                legacy_fallback=hyp_steps,
            )
            # Expand bare ANSI in statement/explanation when possible.
            # Longest codes first; never match a prefix inside 50N / 51P / etc.
            try:
                from protection.ansi_names import format_ansi

                _ansi_expand_codes = (
                    "50NBF",
                    "50BF",
                    "87RGF",
                    "87GT",
                    "50P",
                    "51P",
                    "50N",
                    "51N",
                    "50G",
                    "51G",
                    "67N",
                    "67P",
                    "67G",
                    "21G",
                    "21P",
                    "21N",
                    "87L",
                    "87T",
                    "87B",
                    "87G",
                    "81U",
                    "81O",
                    "81R",
                    "32R",
                    "62BF",
                    "LBB",
                    "50",
                    "51",
                    "21",
                    "67",
                    "79",
                    "86",
                    "27",
                    "59",
                    "46",
                    "48",
                    "49",
                    "68",
                    "78",
                    "25",
                    "87",
                )
                for key in ("statement", "explanation"):
                    text = str(narrative.get(key) or "")
                    for code in _ansi_expand_codes:
                        named = format_ansi(code)
                        if named == code:
                            continue
                        # Token boundary: do not split 51N via code "51".
                        # Also skip already-expanded ``51N (…​)``.
                        text = re.sub(
                            rf"(?<![A-Za-z0-9]){re.escape(code)}(?![A-Za-z0-9])(?!\s*\()",
                            named,
                            text,
                            flags=re.IGNORECASE,
                        )
                    narrative[key] = text
            except Exception:  # noqa: BLE001
                pass

            result.hypotheses.append(
                HypothesisResult(
                    hypothesis_id=hid,
                    status=status,
                    score=round(float(score), 4),
                    confidence=conf,
                    supporting_evidence=supporting,
                    contradicting_evidence=contradicting,
                    missing_evidence=missing,
                    statement=narrative["statement"],
                    explanation=narrative["explanation"],
                    causal_chain=narrative["causal_chain"],
                    recommended_actions=narrative["recommended_actions"],
                    title=_title(hid),
                )
            )

        if not result.hypotheses:
            result.limitations.append("No hypothesis definitions loaded")
            result.primary = HypothesisResult(
                hypothesis_id="UNKNOWN",
                status=HypothesisStatus.INCONCLUSIVE.value,
                score=0.0,
                confidence="INCONCLUSIVE",
                statement="Insufficient structured evidence to form an RCA hypothesis.",
            )
            return result

        # Matrix pack (L1/L2/L3 + LBB) — compound class, checklist, bus guardrail
        from rca.matrix import apply_matrix_to_hypotheses, match_matrix

        matrix_result = match_matrix(evidence_bag)
        apply_matrix_to_hypotheses(result.hypotheses, matrix_result)
        result.matrix = matrix_result.to_dict()
        result.enrichment = dict(result.enrichment or {})
        # L1/L2/L3 deep ladder traces before scenario traces
        deep_tr = list((result.enrichment.get("ladder_deep") or {}).get("traces") or [])
        merged_tr = list(deep_tr) + list(matrix_result.traces or [])
        if merged_tr:
            result.enrichment["matrix_traces"] = merged_tr
        if matrix_result.compound_class:
            result.enrichment["compound_class"] = matrix_result.compound_class
        if matrix_result.matched_scenario_id:
            result.enrichment["matrix_scenario"] = matrix_result.matched_scenario_id
        if matrix_result.level_coverage:
            result.enrichment["level_coverage"] = dict(matrix_result.level_coverage)
        # Taxonomy: L3-only fallback without L1 → do not leave CONFIRMED on zone hyps
        if "l3_fallback_applied" in evidence_bag and "evidence_l1_present" not in evidence_bag:
            for h in result.hypotheses:
                if (
                    h.hypothesis_id in ZONE_PRIMARY_HYPOTHESES
                    and h.status == HypothesisStatus.CONFIRMED.value
                ):
                    h.status = HypothesisStatus.PROBABLE.value
                    h.explanation = (
                        (h.explanation or "")
                        + " Downgraded to PROBABLE — L3 waveform fallback without L1 digital assert."
                    ).strip()

        if result.forced_inconclusive:
            # Policy: disposition primary stays INCONCLUSIVE when settings critical,
            # but surface the best fault-side hypothesis from available data.
            top_fault = next(
                (
                    h
                    for h in sorted(
                        result.hypotheses, key=lambda x: x.score, reverse=True
                    )
                    if h.hypothesis_id in FAULT_SIDE_HYPOTHESES
                    and h.status
                    in (
                        HypothesisStatus.PROBABLE.value,
                        HypothesisStatus.POSSIBLE.value,
                        HypothesisStatus.CONFIRMED.value,
                    )
                ),
                None,
            )
            result.primary = HypothesisResult(
                hypothesis_id="UNKNOWN",
                status=HypothesisStatus.INCONCLUSIVE.value,
                score=0.0,
                confidence="INCONCLUSIVE",
                title=_title("UNKNOWN"),
                missing_evidence=["active_setting_verification"],
                supporting_evidence=list(top_fault.supporting_evidence)
                if top_fault
                else [],
                contradicting_evidence=["critical_setting_inconsistency"],
                statement=(
                    "RCA disposition is INCONCLUSIVE until active settings are verified. "
                    + (
                        f"Available data still favours {_title(top_fault.hypothesis_id)} "
                        f"({top_fault.status}, score {top_fault.score})."
                        if top_fault
                        else "Electrical evidence is incomplete."
                    )
                ),
                explanation=top_fault.explanation if top_fault else "",
                causal_chain=top_fault.causal_chain if top_fault else [],
                recommended_actions=[
                    "Verify active setting group at event time",
                    "Re-run consistency after verification",
                    *(top_fault.recommended_actions[:2] if top_fault else []),
                ],
            )
        else:
            result.primary = self._select_primary(result.hypotheses)
            # Prefer matrix primary when L1/L2/L3 ladder agrees (≥2 layers) or YAML opts in.
            pref = matrix_result.primary_hypothesis
            prefer = bool(getattr(matrix_result, "prefer_primary", False))
            if not prefer:
                for cand in matrix_result.candidates or []:
                    if cand.get("id") == matrix_result.matched_scenario_id:
                        prefer = bool(cand.get("prefer_primary"))
                        break
            if not prefer and matrix_result.matched_scenario_id:
                prefer = matrix_result.matched_scenario_id in {
                    "SC_LBB_CASCADE_COMPOUND",
                    "SC_INRUSH_ENERGIZATION_FALLBACK",
                    "SC_SWITCH_ONTO_FAULT",
                    "SC_XFMR_INTERNAL_THROUGH_EXCLUDED",
                    "SC_BUS_ZONE_REQUIRES_87B",
                }
            agree = int((matrix_result.level_coverage or {}).get("agree_count") or 0)
            if (
                pref
                and prefer
                and result.primary
                and result.primary.hypothesis_id != pref
            ):
                alt = next(
                    (h for h in result.hypotheses if h.hypothesis_id == pref), None
                )
                # Taxonomy: multi-layer agreement may promote from POSSIBLE;
                # single-layer still requires PROBABLE+.
                min_status = (
                    HypothesisStatus.POSSIBLE.value
                    if agree >= 2
                    else HypothesisStatus.PROBABLE.value
                )
                if alt is not None and STATUS_RANK.get(alt.status, 0) >= STATUS_RANK.get(
                    min_status, 0
                ):
                    prev = result.primary.hypothesis_id
                    result.primary = alt
                    result.enrichment = dict(result.enrichment or {})
                    result.enrichment["matrix_primary_override"] = {
                        "from": prev,
                        "to": pref,
                        "ladder": (matrix_result.level_coverage or {}).get("ladder"),
                        "agree_count": agree,
                    }
        return result

    def _select_primary(self, hypotheses: list[HypothesisResult]) -> HypothesisResult:
        ranked = sorted(
            hypotheses,
            key=lambda h: (
                STATUS_RANK.get(h.status, 0),
                h.score,
                1 if h.hypothesis_id != "UNKNOWN" else 0,
            ),
            reverse=True,
        )
        top = ranked[0]
        if top.hypothesis_id == "UNKNOWN" and len(ranked) > 1:
            alt = next((h for h in ranked if h.hypothesis_id != "UNKNOWN"), None)
            if alt and STATUS_RANK.get(alt.status, 0) >= STATUS_RANK.get(
                HypothesisStatus.POSSIBLE.value, 0
            ):
                return alt
        # Prefer Breaker failure only for *local* BF / LBB cascade initiator.
        # A bay that successfully cleared (e.g. HV after LV LBB) may show 50BF
        # digitals — that must not become primary RCA over the zone fault.
        bf = next((h for h in ranked if h.hypothesis_id == "BREAKER_FAILURE"), None)
        if (
            bf is not None
            and top.hypothesis_id
            in ZONE_PRIMARY_HYPOTHESES
            | {
                "INTERTRIP_OPERATION",
                "EXTERNAL_LINE_FAULT",
                "TRANSFORMER_INTERNAL_FAULT",
                "SWITCH_ONTO_FAULT",
            }
            and STATUS_RANK.get(bf.status, 0)
            >= STATUS_RANK.get(HypothesisStatus.PROBABLE.value, 0)
            and bf.score + 0.08 >= top.score
        ):
            support = set(bf.supporting_evidence or [])
            local_bf = "bf_logic_satisfied" in support and "current_persists" in support
            # Initiator cascade only — not upstream RX-only clearance
            cascade_bf = (
                "cascade_lbb_detected" in support
                and "cascade_upstream_clearance" not in support
                and "intertrip_receive_observed" not in support
            )
            if cascade_bf or local_bf:
                return bf
        # Backup / upstream bay that *received* LBB intertrip: primary is
        # transfer-trip clearance, not a local feeder / zone root cause.
        inter = next((h for h in ranked if h.hypothesis_id == "INTERTRIP_OPERATION"), None)
        if (
            inter is not None
            and top.hypothesis_id in ZONE_PRIMARY_HYPOTHESES
            and STATUS_RANK.get(inter.status, 0)
            >= STATUS_RANK.get(HypothesisStatus.POSSIBLE.value, 0)
        ):
            isupport = set(inter.supporting_evidence or [])
            if (
                "intertrip_receive_observed" in isupport
                or "cascade_upstream_clearance" in isupport
            ):
                return inter
        # Prefer Switch onto fault over zone-primary only with strong close/SOTF evidence
        # (not a plain trip with 52a open, and not AR reclaim into fault).
        sotf = next((h for h in ranked if h.hypothesis_id == "SWITCH_ONTO_FAULT"), None)
        if (
            sotf is not None
            and top.hypothesis_id in ZONE_PRIMARY_HYPOTHESES
            and STATUS_RANK.get(sotf.status, 0)
            >= STATUS_RANK.get(HypothesisStatus.PROBABLE.value, 0)
            and sotf.score + 0.05 >= top.score
        ):
            support = set(sotf.supporting_evidence or [])
            # Dedicated SOTF digital or pre-trip close (not AR-only) may win.
            if "sotf_element_asserted" in support:
                return sotf
            if "breaker_close_observed" in support:
                return sotf
        return top

    def _collect_evidence(
        self,
        fault: FaultClassificationResult,
        assessments: list[ProtectionAssessment],
        consistency: ConsistencyResult,
        electrical_flags: dict[str, Any],
    ) -> set[str]:
        bag: set[str] = set()
        ec = getattr(fault, "event_class", None) or electrical_flags.get("event_class")
        if not ec:
            ec_feat = (fault.evidence or {}).get("event_classification")
            if isinstance(ec_feat, dict):
                ec = ec_feat.get("event_class")
        if ec:
            bag.add(f"event_class_{ec}")
            if str(ec) in (
                "ENERGIZATION",
                "MOTOR_START",
                "SWITCHING",
                "DISTURBANCE",
            ):
                bag.add("electrical_no_fault")
                bag.add("dfr_non_fault_event")
                if str(ec) == "ENERGIZATION":
                    bag.add("magnetizing_inrush_possible")
                    bag.add("switching_event_correlated")
                    bag.add("harmonic_evidence")
                elif str(ec) == "MOTOR_START":
                    bag.add("motor_start_possible")
                    bag.add("switching_event_correlated")
                elif str(ec) == "SWITCHING":
                    bag.add("switching_event_correlated")

        # Shunt fault tokens: require CLASSIFIED/PROBABLE type, not an explicit
        # non-fault DFR class. FAULT and UNKNOWN (or missing) event_class both OK.
        _non_fault_ec = str(ec or "") in (
            "ENERGIZATION",
            "MOTOR_START",
            "SWITCHING",
            "DISTURBANCE",
        )
        _ft = str(getattr(fault, "fault_type", "") or "")
        if (
            not _non_fault_ec
            and fault.status in ("CLASSIFIED", "PROBABLE")
            and _ft not in ("", "UNKNOWN")
        ):
            bag.add("fault_classified")
            bag.add(f"fault_type_{fault.fault_type}")
        if (
            not _non_fault_ec
            and fault.status == "CLASSIFIED"
            and _ft not in ("", "UNKNOWN")
        ):
            bag.add("fault_classified_strong")

        any_trip = any(_assessment_tripped(a) for a in assessments)
        any_pickup = any(a.pickup is True for a in assessments)
        # Trip assert only — pickup-alone is not "protection operated" for RCA
        if any_trip:
            bag.add("trip_observed")
            bag.add("protection_operated")
        if any_pickup or any_trip:
            bag.add("protection_responded")
            assert_tok = _protection_assert_token(
                any_pickup=any_pickup, any_trip=any_trip
            )
            if assert_tok:
                bag.add(assert_tok)
        if any(
            a.consistency == "CONSISTENT" and _assessment_tripped(a) for a in assessments
        ):
            bag.add("protection_operated_consistently")
        if any(a.consistency == "CONSISTENT" for a in assessments):
            bag.add("element_behavior_consistent")

        if electrical_flags.get("current_increase") or electrical_flags.get(
            "fault_indicated"
        ):
            bag.add("current_increase_observed")
        if electrical_flags.get("waveform_distortion"):
            bag.add("waveform_distortion")
        if electrical_flags.get("harmonic_evidence"):
            bag.add("harmonic_evidence")
        if electrical_flags.get("no_fault"):
            bag.add("electrical_no_fault")
        if electrical_flags.get("current_persists"):
            bag.add("current_persists")
        if electrical_flags.get("trip_command") or any_trip:
            bag.add("trip_command_observed")
        if electrical_flags.get("intertrip"):
            bag.add("intertrip_signal_observed")
        if electrical_flags.get("intertrip_receive_seen"):
            bag.add("intertrip_signal_observed")
            bag.add("intertrip_receive_observed")
        if electrical_flags.get("intertrip_send_seen"):
            bag.add("intertrip_signal_observed")
            bag.add("intertrip_send_observed")
        if electrical_flags.get("cascade_upstream_clearance"):
            bag.add("cascade_upstream_clearance")
            bag.add("intertrip_signal_observed")
        if electrical_flags.get("comm_channel"):
            bag.add("comm_channel_evidence")
        if electrical_flags.get("switching_correlated"):
            bag.add("switching_event_correlated")
        if electrical_flags.get("external_event_correlated"):
            bag.add("external_event_correlated")
        # LBB / multi-bay cascade (LV BF → HV intertrip clearance) — single incident
        if electrical_flags.get("cascade_lbb_detected"):
            bag.add("cascade_lbb_detected")
            bag.add("scheme_breaker_failure")
            bag.add("trip_command_observed")
            bag.add("intertrip_signal_observed")
            # Upstream/backup clearance only when this end received intertrip
            # (or pipeline already stamped cascade_upstream_clearance).
            rx_only = bool(electrical_flags.get("intertrip_receive_seen")) and not bool(
                electrical_flags.get("intertrip_send_seen")
            )
            if rx_only or electrical_flags.get("cascade_upstream_clearance"):
                bag.add("cascade_upstream_clearance")
                bag.add("intertrip_receive_observed")
            # Only claim local BF logic when persist is evidenced (waveform or
            # explicit Combined Cascade mode) — not from CFG channel names alone.
            if electrical_flags.get("current_persists") and not rx_only:
                bag.add("current_persists")
                bag.add("bf_logic_satisfied")
        # Breaker CLOSE only — pipeline must set breaker_close for a *pre-trip* close.
        # A trip/open 52a change or AR reclaim must not be treated as switch-onto-fault.
        if electrical_flags.get("breaker_close"):
            bag.add("breaker_close_observed")
            bag.add("switching_event_correlated")
        # Autoreclose after trip (79) — reclaim into fault ≠ energize/SOTF
        tl_types = electrical_flags.get("timeline_event_types") or []
        if not isinstance(tl_types, (list, tuple, set)):
            tl_types = []
        has_reclose_tl = "reclose" in {str(t) for t in tl_types}
        has_79 = any(
            str(getattr(a, "element", "") or "").upper() in ("79",)
            and (
                getattr(a, "pickup", None) is True
                or getattr(a, "trip", None) is True
                or str(getattr(a, "actual_operation", "") or "").upper()
                in ("TRIPPED", "PICKED_UP", "OPERATED")
            )
            for a in assessments
        )
        if has_reclose_tl or has_79 or electrical_flags.get("autoreclose"):
            bag.add("autoreclose_issued")
        # Magnetizing inrush / transformer charging (H2 detector)
        det = electrical_flags.get("detectors") if isinstance(electrical_flags.get("detectors"), dict) else {}
        inrush = det.get("magnetizing_inrush") if isinstance(det, dict) else None
        if electrical_flags.get("magnetizing_inrush") or (
            isinstance(inrush, dict) and str(inrush.get("status") or "").upper() == "POSSIBLE"
        ):
            bag.add("magnetizing_inrush_possible")
            bag.add("switching_event_correlated")
            bag.add("harmonic_evidence")
        # Motor start / motor-protection DR (Start I>, 46/48/49, Any Start, …)
        dig_names = electrical_flags.get("digital_channel_names")
        if not isinstance(dig_names, (list, tuple)):
            dig_names = []
        motor = motor_start_context(
            list(dig_names),
            detectors=det if isinstance(det, dict) else {},
            assessments=assessments,
        )
        if motor.get("present"):
            bag.add("motor_protection_present")
        if motor.get("likely") or electrical_flags.get("motor_start"):
            bag.add("motor_start_possible")
            bag.add("switching_event_correlated")
        # Switch-onto-fault (SOTF) digital / channel names
        if _sotf_name_hit(list(dig_names)) or _sotf_from_assessments(assessments):
            bag.add("sotf_element_asserted")
            bag.add("switching_event_correlated")
        # Scheme-library tokens passed via electrical_flags["scheme_tokens"]
        scheme_toks = electrical_flags.get("scheme_tokens")
        if isinstance(scheme_toks, (list, set, tuple)):
            bag |= {str(t) for t in scheme_toks if t}
        elif isinstance(scheme_toks, dict):
            bag |= {str(t) for t in scheme_toks.keys() if t}

        # Composite: close/energize into a shunt fault (not pickup-only inrush).
        # Require named SOTF element or a confirmed *pre-trip* breaker close
        # (pipeline already excludes AR reclaim / post-trip 52a rising).
        if (
            "fault_classified" in bag
            and "protection_operated" in bag
            and "dfr_non_fault_event" not in bag
            and "cascade_lbb_detected" not in bag
            and (
                "sotf_element_asserted" in bag
                or "breaker_close_observed" in bag
            )
        ):
            bag.add("switch_onto_fault_possible")
            bag.add("switch_onto_fault_context")

        if consistency.has_critical_setting_inconsistency:
            bag.add("setting_inconsistency_unverified")
        elif consistency.summary_status == "CONSISTENT":
            bag.add("settings_behavior_consistent")
            bag.add("settings_partial")
        else:
            bag.add("settings_partial")

        bag |= _scheme_tokens_from_assessments(assessments)

        # Local BF logic: 50BF digital + current still flowing (or cascade already set it)
        if (
            "bf_element_operated" in bag
            and "current_persists" in bag
            and "bf_logic_satisfied" not in bag
        ):
            bag.add("bf_logic_satisfied")

        if _through_fault_excluded_from_xfmr(assessments, electrical_flags):
            bag.add("through_fault_excluded")

        dist_info = fault.distance if isinstance(fault.distance, dict) else {}
        if dist_info.get("distance_km") is not None or dist_info.get("value_km") is not None:
            bag.add("distance_estimate_available")
        if dist_info.get("impedance_ohm") is not None or (
            isinstance(dist_info.get("loop_impedance"), dict)
            and dist_info["loop_impedance"].get("magnitude_ohm") is not None
        ):
            bag.add("loop_impedance_available")

        feat = fault.evidence if isinstance(fault.evidence, dict) else {}
        if feat.get("ground"):
            bag.add("ground_involved")

        # Soft shunt-fault token: trip + scheme/electrical evidence proves a fault
        # was cleared even when AG/ABC typing stayed UNKNOWN (unmapped currents,
        # 87T-only DRs). Unlocks matrix rows that require fault_classified without
        # inventing a phase type.
        if (
            not _non_fault_ec
            and "fault_classified" not in bag
            and any_trip
            and (
                str(ec or "") == "FAULT"
                or electrical_flags.get("fault_indicated")
                or electrical_flags.get("current_increase")
                or "differential_operated" in bag
                or "overcurrent_element_operated" in bag
                or "earth_fault_element_operated" in bag
                or "distance_element_operated" in bag
                or "bf_logic_satisfied" in bag
                or "bf_element_operated" in bag
            )
        ):
            bag.add("fault_classified")

        # --- Matrix L3: analogue / sequence components from DR ---
        def _fnum(*keys: str) -> Optional[float]:
            for k in keys:
                v = electrical_flags.get(k)
                if v is None and isinstance(feat, dict):
                    v = feat.get(k)
                try:
                    if v is not None:
                        return float(v)
                except (TypeError, ValueError):
                    continue
            return None

        i_max = _fnum("I_max_a", "I_fault_a")
        i2 = _fnum("I2", "I2_a")
        i0 = _fnum("I0", "I0_a")
        if i_max and i_max > 0:
            if i2 is not None and i2 >= 0.15 * i_max:
                bag.add("negative_sequence_elevated")
                els = {
                    str(getattr(a, "element", "") or "").upper() for a in assessments
                }
                if any(e == "46" or e.startswith("46") for e in els):
                    bag.add("unbalance_protection_operated")
            if i0 is not None and i0 >= 0.15 * i_max:
                bag.add("zero_sequence_elevated")
                bag.add("ground_involved")
        v_min = _fnum("V_min_v")
        v_max = _fnum("V_max_v")
        if v_min is not None and v_max is not None and v_max > 0 and v_min <= 0.85 * v_max:
            bag.add("voltage_sag_observed")
        det = (
            electrical_flags.get("detectors")
            if isinstance(electrical_flags.get("detectors"), dict)
            else {}
        )
        ct_sat = det.get("ct_saturation") if isinstance(det, dict) else None
        if isinstance(ct_sat, dict) and str(ct_sat.get("status") or "").upper() in (
            "POSSIBLE",
            "LIKELY",
            "CONFIRMED",
        ):
            bag.add("ct_saturation_suspected")

        # --- Matrix L2: SOE / sequence markers from timeline ---
        tl = {str(t) for t in (electrical_flags.get("timeline_event_types") or [])}
        if electrical_flags.get("successful_clearing") or "current_interruption" in tl:
            bag.add("successful_clearing")
        if electrical_flags.get("breaker_open_confirmed"):
            bag.add("breaker_open_confirmed")
        elif (
            "current_interruption" in tl
            and not electrical_flags.get("current_persists")
            and ("protection_trip" in tl or "breaker_trip_command" in tl or any_trip)
        ):
            bag.add("breaker_open_confirmed")
            bag.add("successful_clearing")
        if "fault_inception" in tl:
            bag.add("fault_inception_observed")
        if electrical_flags.get("settings_verified") or electrical_flags.get(
            "engineer_verified_active_group"
        ):
            bag.add("settings_verified")

        # Layer presence (Excel L1 / L2 / L3) — used by match_matrix ladder
        from rca.matrix import layer_tokens_present

        for layer, present in layer_tokens_present(bag).items():
            if present:
                bag.add(f"evidence_{layer.lower()}_present")

        return bag

    def _evaluate_evidence(
        self,
        hid: str,
        required: list[str],
        bag: set[str],
        fault: FaultClassificationResult,
    ) -> tuple[list[str], list[str], list[str]]:
        supporting = [e for e in required if e in bag]
        missing = [e for e in required if e not in bag]

        extras: list[str] = []
        # Generic fault-side extras only for zone primaries (not lightning/vegetation/cable)
        if hid in ZONE_PRIMARY_HYPOTHESES:
            for tok in (
                "fault_classified",
                "fault_classified_strong",
                "current_increase_observed",
                "protection_pickup_with_trip",
                "protection_pickup_asserted",
                "protection_trip_asserted",
                "protection_operated",
                "protection_operated_consistently",
                "protection_responded",
                "settings_behavior_consistent",
                "element_behavior_consistent",
                "ground_involved",
            ):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid in LINE_FEEDER_CAUSE_HYPOTHESES:
            for tok in CAUSE_EVIDENCE_TOKENS.get(hid, frozenset()):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
            # Circuit-zone context only — do not treat any classified fault as vegetation/etc.
            if _hypothesis_scheme_fit(hid, bag) in ("match", "pending"):
                if "fault_classified" in bag and "fault_classified" not in supporting:
                    extras.append("fault_classified")
        if hid == "EXTERNAL_LINE_FAULT":
            for tok in (
                "distance_element_operated",
                "distance_estimate_available",
                "loop_impedance_available",
                "scheme_distance",
                "line_diff_operated",
                "scheme_line_diff",
            ):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "INTERNAL_FEEDER_FAULT":
            for tok in (
                "overcurrent_element_operated",
                "earth_fault_element_operated",
                "scheme_overcurrent",
                "scheme_earth_fault",
                "directional_element_operated",
            ):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "TRANSFORMER_INTERNAL_FAULT":
            for tok in (
                "transformer_diff_operated",
                "differential_operated",
                "scheme_xfmr_diff",
                "through_fault_excluded",
            ):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "BUS_ZONE_FAULT":
            for tok in ("bus_diff_operated", "scheme_bus_diff", "differential_operated"):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "GENERATOR_INTERNAL_FAULT":
            for tok in ("generator_diff_operated", "scheme_gen_diff", "differential_operated"):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "EXTERNAL_GRID_DISTURBANCE":
            for tok in (
                "voltage_element_operated",
                "frequency_element_operated",
                "scheme_voltage",
                "scheme_frequency",
            ):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "SWITCHING_TRANSIENT":
            for tok in (
                "power_swing_element_operated",
                "scheme_power_swing",
                "reclose_or_lockout_operated",
                "switching_event_correlated",
                "magnetizing_inrush_possible",
                "transformer_diff_picked_up",
                "harmonic_evidence",
            ):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "SWITCH_ONTO_FAULT":
            for tok in (
                "switch_onto_fault_possible",
                "switch_onto_fault_context",
                "sotf_element_asserted",
                "breaker_close_observed",
                "switching_event_correlated",
                "fault_classified",
                "fault_classified_strong",
                "protection_operated",
                "protection_pickup_with_trip",
                "protection_trip_asserted",
                "current_increase_observed",
                "overcurrent_element_operated",
                "distance_element_operated",
                "differential_operated",
                "ground_involved",
            ):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "MOTOR_START":
            for tok in (
                "motor_start_possible",
                "motor_protection_present",
                "scheme_motor",
                "motor_element_operated",
                "overcurrent_element_operated",
                "protection_pickup_asserted",
                "current_increase_observed",
                "switching_event_correlated",
            ):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "BREAKER_FAILURE":
            for tok in (
                "bf_logic_satisfied",
                "scheme_breaker_failure",
                "current_persists",
                "trip_command_observed",
                "cascade_lbb_detected",
                "cascade_upstream_clearance",
                "intertrip_signal_observed",
                "intertrip_send_observed",
            ):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "COMMUNICATION_FAILURE":
            for tok in (
                "comm_channel_evidence",
                "scheme_pilot",
                "scheme_profile_pilot_pott",
                "scheme_digitals_incomplete",
            ):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "INTERTRIP_OPERATION":
            for tok in (
                "intertrip_signal_observed",
                "intertrip_receive_observed",
                "intertrip_send_observed",
                "cascade_upstream_clearance",
                "scheme_pilot",
                "protection_trip_asserted",
                "protection_operated",
            ):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "RELAY_MISOPERATION":
            for tok in ("trip_observed", "electrical_no_fault"):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        supporting = supporting + extras
        # Prefer explicit pickup / trip / pickup-with-trip over vague "responded"
        _assert_specific = (
            "protection_pickup_with_trip",
            "protection_pickup_asserted",
            "protection_trip_asserted",
        )
        if any(t in supporting for t in _assert_specific):
            supporting = [
                t
                for t in supporting
                if t
                not in (
                    "protection_responded",
                    # When both pickup+trip, the combined token is enough
                    *(
                        ("protection_operated",)
                        if "protection_pickup_with_trip" in supporting
                        else ()
                    ),
                )
            ]

        contradicting: list[str] = []
        if hid == "RELAY_MISOPERATION" and "fault_classified" in bag:
            contradicting.append("fault_classified")
        if hid == "EXTERNAL_LINE_FAULT" and "electrical_no_fault" in bag:
            contradicting.append("electrical_no_fault")
        # Scheme contradictions
        if hid == "EXTERNAL_LINE_FAULT":
            if (
                "overcurrent_element_operated" in bag
                and "distance_element_operated" not in bag
                and "distance_estimate_available" not in bag
                and "line_diff_operated" not in bag
            ):
                contradicting.append("feeder_oc_without_distance_context")
            if "bus_diff_operated" in bag or "generator_diff_operated" in bag:
                contradicting.append("non_line_differential_operated")
            if "transformer_diff_operated" in bag and "line_diff_operated" not in bag:
                contradicting.append("transformer_diff_operated")
            if (
                "intertrip_receive_observed" in bag
                or "cascade_upstream_clearance" in bag
            ):
                contradicting.append("cleared_via_intertrip_receive")
        if hid == "INTERNAL_FEEDER_FAULT":
            if "distance_element_operated" in bag and "overcurrent_element_operated" not in bag:
                contradicting.append("distance_primary_without_oc")
            if "differential_operated" in bag and "earth_fault_element_operated" not in bag:
                # 87RGF counts as EF; other diffs should not pick feeder
                if "transformer_diff_operated" in bag or "bus_diff_operated" in bag or "generator_diff_operated" in bag or "line_diff_operated" in bag:
                    contradicting.append("differential_scheme_operated")
            # HV/backup clearance via received LBB intertrip is not a local feeder root cause
            if (
                "intertrip_receive_observed" in bag
                or "cascade_upstream_clearance" in bag
            ):
                contradicting.append("cleared_via_intertrip_receive")
        if hid == "TRANSFORMER_INTERNAL_FAULT":
            if "transformer_diff_operated" not in bag and "differential_operated" not in bag:
                if "distance_element_operated" in bag or "overcurrent_element_operated" in bag:
                    contradicting.append("non_differential_scheme_operated")
            if "bus_diff_operated" in bag or "line_diff_operated" in bag or "generator_diff_operated" in bag:
                if "transformer_diff_operated" not in bag:
                    contradicting.append("wrong_differential_family")
        if hid == "BUS_ZONE_FAULT" and "bus_diff_operated" not in bag:
            contradicting.append("bus_diff_not_operated")
        if hid == "GENERATOR_INTERNAL_FAULT" and "generator_diff_operated" not in bag:
            contradicting.append("generator_diff_not_operated")
        if hid == "BREAKER_FAILURE" and "bf_logic_satisfied" not in bag:
            contradicting.append("bf_element_not_operated")
        if hid in LINE_FEEDER_CAUSE_HYPOTHESES:
            fit = _hypothesis_scheme_fit(hid, bag)
            if fit == "mismatch":
                contradicting.append("scheme_zone_mismatch")
            needed = CAUSE_EVIDENCE_TOKENS.get(hid, frozenset())
            if needed and not (bag & needed):
                contradicting.append("cause_specific_evidence_absent")
        if "setting_inconsistency_unverified" in bag and hid == "RELAY_MISOPERATION":
            contradicting.append("setting_inconsistency_unverified")
        if hid == "UNKNOWN" and fault.status == "CLASSIFIED":
            contradicting.append("fault_classified")
        return supporting, contradicting, missing

    def _fault_side_base(self, bag: set[str]) -> float:
        score = 0.0
        if "fault_classified" in bag:
            score += 0.35
        if "fault_classified_strong" in bag:
            score += 0.08
        if "current_increase_observed" in bag:
            score += 0.15
        if "protection_operated" in bag:
            score += 0.15
        elif "protection_operated_consistently" in bag:
            score += 0.15
        elif "protection_responded" in bag:
            score += 0.08
        if "protection_operated_consistently" in bag and "protection_operated" in bag:
            score += 0.05  # bonus when operate also matches settings
        if "settings_behavior_consistent" in bag:
            score += 0.08
        return score

    def _deterministic_score(
        self, hid: str, bag: set[str], fault: FaultClassificationResult
    ) -> float:
        if hid == "EXTERNAL_LINE_FAULT":
            score = self._fault_side_base(bag)
            # Line / distance / line-diff boosts
            if "distance_element_operated" in bag:
                score += 0.22
            if "line_diff_operated" in bag:
                score += 0.24
            if "distance_estimate_available" in bag:
                score += 0.10
            if "loop_impedance_available" in bag:
                score += 0.05
            # Without line context, do not outrank feeder/OC / other diffs
            if (
                "distance_element_operated" not in bag
                and "distance_estimate_available" not in bag
                and "line_diff_operated" not in bag
            ):
                score -= 0.18
                if "overcurrent_element_operated" in bag or "earth_fault_element_operated" in bag:
                    score -= 0.10
                if "transformer_diff_operated" in bag or "bus_diff_operated" in bag or "generator_diff_operated" in bag:
                    score -= 0.20
            return min(max(score, 0.0), 1.0)

        if hid == "INTERNAL_FEEDER_FAULT":
            score = self._fault_side_base(bag)
            if "overcurrent_element_operated" in bag:
                score += 0.22
            elif "overcurrent_element_picked_up" in bag:
                score += 0.08  # pickup-only — weak for feeder fault
            if "earth_fault_element_operated" in bag:
                score += 0.18
            elif "earth_fault_element_picked_up" in bag:
                score += 0.08
            if "directional_element_operated" in bag:
                score += 0.08
            elif "directional_element_picked_up" in bag:
                score += 0.03
            if "scheme_overcurrent" in bag or "scheme_earth_fault" in bag:
                score += 0.05
            if "distance_element_operated" in bag:
                score -= 0.20
            elif "distance_estimate_available" in bag and "overcurrent_element_operated" not in bag:
                score -= 0.08
            if "line_diff_operated" in bag or "bus_diff_operated" in bag or "generator_diff_operated" in bag:
                score -= 0.25
            if "transformer_diff_operated" in bag:
                score -= 0.25
            if (
                "distance_element_operated" not in bag
                and "differential_operated" not in bag
                and "fault_classified" in bag
            ):
                score += 0.06
            # Motor start DRs are not feeder shunt faults
            if "motor_start_possible" in bag:
                score -= 0.40
            # Explicit SOTF / close-into-fault → prefer SWITCH_ONTO_FAULT as primary
            if "sotf_element_asserted" in bag:
                score -= 0.35
            elif "switch_onto_fault_possible" in bag:
                score -= 0.28
            # LBB cascade: HV/feeder trip is consequence — BF is primary (initiator)
            if "cascade_lbb_detected" in bag:
                score -= 0.30
            # Upstream bay cleared after receiving intertrip — not local feeder RCA
            if (
                "intertrip_receive_observed" in bag
                or "cascade_upstream_clearance" in bag
            ):
                score -= 0.40
            return min(max(score, 0.0), 1.0)

        if hid == "CABLE_FAULT":
            fit = _hypothesis_scheme_fit(hid, bag)
            if fit == "mismatch":
                return 0.08
            base = 0.18 if "fault_classified" in bag else 0.10
            if "cable_asset_confirmed" in bag:
                base += 0.40
            if "distance_element_operated" in bag or "line_diff_operated" in bag:
                base += 0.05
            if "overcurrent_element_operated" in bag or "earth_fault_element_operated" in bag:
                base += 0.05
            return min(base, 1.0)

        if hid == "LIGHTNING":
            if _hypothesis_scheme_fit(hid, bag) == "mismatch":
                return 0.06
            if "lightning_evidence" in bag:
                return 0.72 if "fault_classified" in bag else 0.55
            return 0.14 if "fault_classified" in bag else 0.08

        if hid == "VEGETATION":
            if _hypothesis_scheme_fit(hid, bag) == "mismatch":
                return 0.06
            if "field_report_vegetation" in bag:
                return 0.72 if "fault_classified" in bag else 0.55
            return 0.14 if "fault_classified" in bag else 0.08

        if hid == "INSULATION_FLASHOVER":
            if _hypothesis_scheme_fit(hid, bag) == "mismatch":
                return 0.06
            if "insulation_evidence" in bag:
                return 0.70 if "fault_classified" in bag else 0.50
            return 0.14 if "fault_classified" in bag else 0.08

        if hid == "TRANSFORMER_INTERNAL_FAULT":
            # Pickup-only 87 during inrush/charging is not an internal-fault operate
            if "magnetizing_inrush_possible" in bag and "transformer_diff_operated" not in bag:
                return 0.12
            if "transformer_diff_operated" in bag:
                base = 0.82 if "fault_classified" in bag else 0.60
                if "magnetizing_inrush_possible" in bag:
                    base = min(base, 0.45)  # trip during inrush still needs restrain review
                if "through_fault_excluded" in bag:
                    base = min(base + 0.12, 0.95)
                return base
            if "differential_operated" in bag and "bus_diff_operated" not in bag and "line_diff_operated" not in bag and "generator_diff_operated" not in bag:
                return 0.55
            if "transformer_diff_picked_up" in bag:
                return 0.22
            return 0.10

        if hid == "BUS_ZONE_FAULT":
            if "bus_diff_operated" in bag:
                return 0.85 if "fault_classified" in bag else 0.65
            return 0.08

        if hid == "GENERATOR_INTERNAL_FAULT":
            if "generator_diff_operated" in bag:
                return 0.85 if "fault_classified" in bag else 0.65
            return 0.08

        if hid == "EXTERNAL_GRID_DISTURBANCE":
            score = 0.15
            if "voltage_element_operated" in bag:
                score += 0.35
            if "frequency_element_operated" in bag:
                score += 0.35
            if "fault_classified" in bag and "overcurrent_element_operated" not in bag:
                score += 0.05
            if "distance_element_operated" in bag or "differential_operated" in bag:
                score -= 0.15
            return min(max(score, 0.0), 1.0)

        if hid == "SWITCHING_TRANSIENT":
            score = 0.12
            if "power_swing_element_operated" in bag:
                score += 0.40
            if "reclose_or_lockout_operated" in bag:
                score += 0.15
            if "switching_event_correlated" in bag:
                score += 0.30
            # Transformer energization / magnetizing inrush (87 pickup, no trip)
            if "magnetizing_inrush_possible" in bag:
                score += 0.40
            if (
                "transformer_diff_picked_up" in bag
                and "transformer_diff_operated" not in bag
            ):
                score += 0.18
            # Prefer dedicated MOTOR_START when motor context is present
            if "motor_start_possible" in bag:
                score -= 0.25
            # Real trip into a classified fault → Switch onto fault / zone hyps, not energization
            if "fault_classified" in bag and "protection_operated" in bag:
                score -= 0.50
            return min(max(score, 0.0), 1.0)

        if hid == "SWITCH_ONTO_FAULT":
            score = 0.08
            if "fault_classified" in bag:
                score += 0.28
            if "fault_classified_strong" in bag:
                score += 0.08
            if "protection_operated" in bag or "trip_observed" in bag:
                score += 0.22
            if "sotf_element_asserted" in bag:
                score += 0.32
            if "breaker_close_observed" in bag:
                score += 0.18
            if "switch_onto_fault_possible" in bag:
                score += 0.12
            if (
                "switching_event_correlated" in bag
                and "protection_operated" in bag
                and ("sotf_element_asserted" in bag or "breaker_close_observed" in bag)
            ):
                score += 0.08
            if "current_increase_observed" in bag:
                score += 0.06
            # Pure energization / motor start (no trip) must not look like SOTF
            if "dfr_non_fault_event" in bag or "electrical_no_fault" in bag:
                score -= 0.55
            if "magnetizing_inrush_possible" in bag and "protection_operated" not in bag:
                score -= 0.40
            if "motor_start_possible" in bag and "protection_operated" not in bag:
                score -= 0.30
            # BF / LBB cascade clearance is not switch-onto-fault
            if "cascade_lbb_detected" in bag or "bf_logic_satisfied" in bag:
                score -= 0.50
            # AR reclaim alone (no pre-trip close / SOTF digital) → not SOTF
            if (
                "autoreclose_issued" in bag
                and "sotf_element_asserted" not in bag
                and "breaker_close_observed" not in bag
            ):
                score -= 0.45
            if (
                "sotf_element_asserted" not in bag
                and "breaker_close_observed" not in bag
            ):
                score -= 0.40
            return min(max(score, 0.0), 1.0)

        if hid == "MOTOR_START":
            score = 0.10
            if "motor_start_possible" in bag:
                score += 0.48
            if "motor_protection_present" in bag or "scheme_motor" in bag:
                score += 0.12
            if "motor_element_operated" in bag:
                score += 0.10
            if "overcurrent_element_operated" in bag and "protection_operated" not in bag:
                score += 0.12
            if "protection_pickup_asserted" in bag and "protection_operated" not in bag:
                score += 0.08
            if "current_increase_observed" in bag:
                score += 0.06
            if "fault_classified" in bag:
                score -= 0.12
            if "magnetizing_inrush_possible" in bag:
                score -= 0.20
            return min(max(score, 0.0), 1.0)

        if hid == "RELAY_MISOPERATION":
            if "setting_inconsistency_unverified" in bag:
                return 0.1
            if "electrical_no_fault" in bag and "trip_observed" in bag:
                return 0.7
            if "fault_classified" in bag:
                return 0.15
            return 0.2

        if hid == "CT_SATURATION":
            # Common false-trip path on differential schemes (external fault + CT sat)
            base = 0.12
            if "transformer_diff_operated" in bag or "bus_diff_operated" in bag or "generator_diff_operated" in bag or "line_diff_operated" in bag:
                base = 0.28
            if "waveform_distortion" in bag:
                base += 0.28
            if "harmonic_evidence" in bag:
                base += 0.28
            return min(base, 1.0)
        if hid == "BREAKER_FAILURE":
            score = 0.15
            if "bf_logic_satisfied" in bag:
                score += 0.45
            if "trip_command_observed" in bag:
                score += 0.15
            if "current_persists" in bag:
                score += 0.25
            # Multi-bay LBB cascade (initiator BF + upstream intertrip clearance)
            if "cascade_lbb_detected" in bag:
                score += 0.22
            # 50BF digital alone on a bay that cleared is not local breaker failure
            # (typical HV upstream trip after LV LBB — zone fault is primary).
            if (
                "bf_logic_satisfied" in bag
                and "current_persists" not in bag
                and "cascade_lbb_detected" not in bag
            ):
                score -= 0.42
            if "cascade_upstream_clearance" in bag and "current_persists" not in bag:
                score -= 0.25
            return min(max(score, 0.0), 1.0)
        if hid == "INTERTRIP_OPERATION":
            score = 0.12
            if "intertrip_signal_observed" in bag:
                score += 0.40
            # Backup / upstream end: receiving LBB intertrip *is* the primary story
            if (
                "intertrip_receive_observed" in bag
                or "cascade_upstream_clearance" in bag
            ):
                score += 0.30
            # Initiator LBB cascade: intertrip is only the transfer step
            elif "cascade_lbb_detected" in bag or "intertrip_send_observed" in bag:
                score -= 0.35
            return min(max(score, 0.0), 1.0)
        if hid == "PROTECTION_SETTING_ERROR":
            return 0.55 if "setting_inconsistency_unverified" in bag else 0.2
        # Full Excel matrix — token-gated supporting hypotheses
        _matrix_token_hyps: dict[str, tuple[str, ...]] = {
            "MOTOR_LOCKED_ROTOR": ("locked_rotor_indicated", "motor_stall_indicated"),
            "MOTOR_LOAD_JAM": ("load_jam_indicated", "motor_stall_indicated"),
            "HIGH_IMPEDANCE_FAULT": ("high_impedance_fault_indicated", "hif_suspected"),
            "INTERMITTENT_EARTH_FAULT": (
                "intermittent_earth_indicated",
                "transient_earth_indicated",
            ),
            "TEMPORARY_FAULT_RECLOSE": ("autoreclose_success", "reclose_successful"),
            "PERSISTENT_FAULT_RECLOSE": ("autoreclose_fail", "reclose_unsuccessful"),
            "OVEREXCITATION": ("overflux_operated", "vhz_elevated"),
            "THERMAL_OVERLOAD": (
                "thermal_overload_indicated",
                "thermal_overload_operated",
            ),
            "PHASE_LOSS": ("phase_loss_indicated", "open_phase_indicated"),
            "NEGATIVE_SEQUENCE": (
                "negative_sequence_elevated",
                "unbalance_protection_operated",
            ),
            "LOSS_OF_EXCITATION": (
                "loss_of_excitation_operated",
                "underexcitation_indicated",
            ),
            "FREQUENCY_EVENT": ("frequency_protection_operated", "frequency_anomaly"),
            "OUT_OF_STEP": ("out_of_step_operated", "pole_slip_indicated"),
            "ACCIDENTAL_ENERGIZATION": (
                "accidental_energization_indicated",
                "generator_offline_energized",
            ),
            "CAPACITOR_BANK_FAULT": (
                "capacitor_unbalance_operated",
                "capacitor_fault_indicated",
            ),
            "OVERVOLTAGE": ("overvoltage_operated", "overvoltage_indicated"),
            "TRIP_CIRCUIT_FAILURE": ("trip_circuit_fail", "tc_supervision_alarm"),
            "BREAKER_MECHANICAL_FAILURE": ("breaker_stuck", "breaker_mechanical_fail"),
        }
        if hid in _matrix_token_hyps:
            toks = _matrix_token_hyps[hid]
            if any(t in bag for t in toks):
                return 0.78 if "protection_operated" in bag or "fault_classified" in bag else 0.62
            return 0.08
        if hid == "UNKNOWN":
            if fault.status in ("CLASSIFIED", "PROBABLE"):
                return 0.15
            return 0.35
        if hid in FAULT_SIDE_HYPOTHESES:
            return 0.20 if "fault_classified" in bag else 0.10
        return 0.25 if "fault_classified" in bag else 0.15

    def _consistency_score(self, hid: str, consistency: ConsistencyResult) -> float:
        if consistency.rca_must_remain_inconclusive:
            return 0.1 if hid != "PROTECTION_SETTING_ERROR" else 0.6
        if consistency.summary_status == "CONSISTENT":
            # Consistent protection supports plant-fault hypotheses, not equally all of them
            if hid in (
                "EXTERNAL_LINE_FAULT",
                "INTERNAL_FEEDER_FAULT",
                "TRANSFORMER_INTERNAL_FAULT",
                "BUS_ZONE_FAULT",
                "GENERATOR_INTERNAL_FAULT",
                "BREAKER_FAILURE",
                "SWITCH_ONTO_FAULT",
            ):
                return 0.80
            if hid in FAULT_SIDE_HYPOTHESES:
                return 0.55
            return 0.5
        if consistency.summary_status == "INCONSISTENT":
            return (
                0.7
                if hid in ("PROTECTION_SETTING_ERROR", "RELAY_CONFIGURATION_ERROR")
                else 0.3
            )
        return 0.4

    def _electrical_score(
        self,
        hid: str,
        fault: FaultClassificationResult,
        flags: dict[str, Any],
        bag: Optional[set[str]] = None,
    ) -> float:
        bag = bag or set()
        if fault.status == "CLASSIFIED":
            if hid == "EXTERNAL_LINE_FAULT":
                if (
                    "distance_element_operated" in bag
                    or "distance_estimate_available" in bag
                    or "line_diff_operated" in bag
                ):
                    return 0.90
                if "overcurrent_element_operated" in bag and "distance_element_operated" not in bag:
                    return 0.45
                return 0.55
            if hid == "INTERNAL_FEEDER_FAULT":
                if "sotf_element_asserted" in bag:
                    return 0.40
                if "bus_diff_operated" in bag or "generator_diff_operated" in bag or "line_diff_operated" in bag:
                    return 0.30
                if "transformer_diff_operated" in bag:
                    return 0.35
                if "overcurrent_element_operated" in bag or "earth_fault_element_operated" in bag:
                    return 0.90
                if "distance_element_operated" in bag and "overcurrent_element_operated" not in bag:
                    return 0.40
                return 0.70
            if hid == "CABLE_FAULT":
                if _hypothesis_scheme_fit(hid, bag) == "mismatch":
                    return 0.15
                return 0.45 if "cable_asset_confirmed" in bag else 0.25
            if hid in ("LIGHTNING", "VEGETATION", "INSULATION_FLASHOVER"):
                if _hypothesis_scheme_fit(hid, bag) == "mismatch":
                    return 0.12
                needed = CAUSE_EVIDENCE_TOKENS.get(hid, frozenset())
                return 0.75 if bag & needed else 0.25
            if hid == "TRANSFORMER_INTERNAL_FAULT":
                return 0.92 if "transformer_diff_operated" in bag else (
                    0.50 if "differential_operated" in bag else 0.25
                )
            if hid == "BUS_ZONE_FAULT":
                return 0.92 if "bus_diff_operated" in bag else 0.20
            if hid == "GENERATOR_INTERNAL_FAULT":
                return 0.92 if "generator_diff_operated" in bag else 0.20
            if hid == "EXTERNAL_GRID_DISTURBANCE":
                if "voltage_element_operated" in bag or "frequency_element_operated" in bag:
                    return 0.80
                return 0.40
            if hid == "SWITCH_ONTO_FAULT":
                if "cascade_lbb_detected" in bag or "bf_logic_satisfied" in bag:
                    return 0.20
                if (
                    "autoreclose_issued" in bag
                    and "sotf_element_asserted" not in bag
                    and "breaker_close_observed" not in bag
                ):
                    return 0.25
                if "sotf_element_asserted" in bag:
                    return 0.92
                if "switch_onto_fault_possible" in bag and "breaker_close_observed" in bag:
                    return 0.85
                if "breaker_close_observed" in bag and "protection_operated" in bag:
                    return 0.80
                return 0.25
            if hid == "BREAKER_FAILURE":
                return 0.85 if "bf_logic_satisfied" in bag else 0.25
            if hid == "CT_SATURATION":
                if "transformer_diff_operated" in bag or "bus_diff_operated" in bag:
                    return 0.45
                return 0.30
            if hid in FAULT_SIDE_HYPOTHESES:
                return 0.35
            if hid == "RELAY_MISOPERATION":
                return 0.2
            return 0.35
        if fault.status == "PROBABLE":
            if hid == "EXTERNAL_LINE_FAULT":
                return 0.70 if ("distance_element_operated" in bag or "line_diff_operated" in bag) else 0.40
            if hid == "INTERNAL_FEEDER_FAULT":
                return 0.70 if "overcurrent_element_operated" in bag or "earth_fault_element_operated" in bag else 0.55
            if hid in ("BUS_ZONE_FAULT", "GENERATOR_INTERNAL_FAULT", "TRANSFORMER_INTERNAL_FAULT"):
                return 0.65
            return 0.5
        if flags.get("no_fault") and hid == "RELAY_MISOPERATION":
            return 0.7
        return 0.3

    def _narrative(
        self,
        hid: str,
        status: str,
        fault: FaultClassificationResult,
        supporting: list[str],
        missing: list[str],
        bag: set[str],
        consistency: ConsistencyResult,
        *,
        assessments: Optional[list[ProtectionAssessment]] = None,
    ) -> dict[str, Any]:
        ft = fault.fault_type if fault.fault_type and fault.fault_type != "UNKNOWN" else None
        fault_bit = f"{ft} fault" if ft else "disturbance"
        title = _title(hid)
        asses = list(assessments or [])

        if hid == "EXTERNAL_LINE_FAULT":
            parts = []
            if "fault_classified" in bag:
                parts.append(f"COMTRADE indicates a {fault_bit}")
            dist_ph = _family_assert_phrase(asses, _FAMILY_DISTANCE)
            if dist_ph:
                parts.append(dist_ph)
            elif "distance_element_operated" in bag:
                parts.append("distance element (21) trip asserted")
            line_ph = _family_assert_phrase(asses, _FAMILY_LINE_DIFF)
            if line_ph:
                parts.append(line_ph)
            elif "line_diff_operated" in bag:
                parts.append("line differential (87L) trip asserted")
            if "distance_estimate_available" in bag:
                parts.append("a location estimate is available")
            if "current_increase_observed" in bag:
                parts.append("elevated phase/ground current observed")
            _prot = _protection_assert_phrase(bag)
            if _prot:
                parts.append(_prot)
            if "protection_operated_consistently" in bag:
                parts.append("operate also consistent with settings")
            statement = (
                f"{title} is {status} based on: " + "; ".join(parts) + "."
                if parts
                else f"{title} ranked {status} from available analysis fields."
            )
            actions = [
                a
                for a in (
                    "Confirm faulted line / circuit section in the field",
                    "Verify distance reach / line parameters for location estimate"
                    if (
                        "distance_element_operated" in bag
                        or "distance_estimate_available" in bag
                    )
                    else None,
                    "Review 87L operate/restraint" if "line_diff_operated" in bag else None,
                    "Confirm breaker opened and fault cleared"
                    if "trip_observed" in bag
                    else None,
                    f"Obtain: {', '.join(missing[:3])}" if missing else None,
                )
                if a
            ]
            return {
                "statement": statement,
                "explanation": (
                    "Line / protected-circuit hypothesis — boosted for 21 or 87L; "
                    "demoted for OC/EF-only or bus/xfmr/gen diffs."
                ),
                "causal_chain": [
                    c
                    for c in (
                        f"Fault classification: {fault.status} ({ft or 'UNKNOWN'})",
                        dist_ph or (
                            "Distance element operated"
                            if "distance_element_operated" in bag
                            else None
                        ),
                        line_ph or (
                            "Line differential operated"
                            if "line_diff_operated" in bag
                            else None
                        ),
                        f"Consistency summary: {consistency.summary_status}",
                    )
                    if c
                ],
                "recommended_actions": actions or ["Engineer review of primary evidence"],
            }

        if hid == "INTERNAL_FEEDER_FAULT":
            parts = []
            if "fault_classified" in bag:
                parts.append(f"COMTRADE indicates a {fault_bit}")
            # Exact ANSI codes only — never invent 67N when only 50N/51N asserted
            oc_ph = _family_assert_phrase(asses, _FAMILY_OVERCURRENT) or _element_assert_phrase(
                bag,
                operated_tok="overcurrent_element_operated",
                pickup_tok="overcurrent_element_picked_up",
                label="overcurrent element",
            )
            if oc_ph:
                parts.append(oc_ph)
            ef_ph = _family_assert_phrase(asses, _FAMILY_EARTH_FAULT) or _element_assert_phrase(
                bag,
                operated_tok="earth_fault_element_operated",
                pickup_tok="earth_fault_element_picked_up",
                label="earth-fault element",
            )
            if ef_ph:
                parts.append(ef_ph)
            dir_family = frozenset({"67", "67P"})  # 67N already under earth-fault family
            dir_ph = _family_assert_phrase(asses, dir_family) or _element_assert_phrase(
                bag,
                operated_tok="directional_element_operated",
                pickup_tok="directional_element_picked_up",
                label="directional element",
            )
            if dir_ph:
                parts.append(dir_ph)
            if "current_increase_observed" in bag:
                parts.append("elevated phase/ground current observed")
            _prot = _protection_assert_phrase(bag)
            if _prot:
                parts.append(_prot)
            if "protection_operated_consistently" in bag:
                parts.append("operate also consistent with settings")
            # If intertrip/cascade also present, say so — do not hide it behind OC trip
            if "intertrip_receive_observed" in bag or "cascade_upstream_clearance" in bag:
                parts.append(
                    "intertrip RECEIVE also present — feeder OC may be clearance consequence, "
                    "not standalone root cause (see Intertrip / Breaker-failure hypotheses)"
                )
            elif "cascade_lbb_detected" in bag or "intertrip_send_observed" in bag:
                parts.append(
                    "LBB cascade / intertrip SEND also present — check Breaker-failure as primary"
                )
            statement = (
                f"{title} is {status} based on: " + "; ".join(parts) + "."
                if parts
                else f"{title} ranked {status} from available analysis fields."
            )
            actions = [
                a
                for a in (
                    "Confirm faulted feeder / bay equipment in the field",
                    "Review OC/EF/directional pickup and timing vs verified settings",
                    "If intertrip/LBB digitals exist, compare against Breaker-failure / Intertrip RCA"
                    if (
                        "intertrip_signal_observed" in bag
                        or "cascade_lbb_detected" in bag
                    )
                    else None,
                    "Confirm breaker opened and fault cleared"
                    if "trip_observed" in bag
                    else None,
                    f"Obtain: {', '.join(missing[:3])}" if missing else None,
                )
                if a
            ]
            return {
                "statement": statement,
                "explanation": (
                    "Feeder / local-circuit hypothesis — boosted for 50/51/EF/67 trip; "
                    "pickup-only is stated as pickup, not trip/operate. "
                    "When intertrip or LBB cascade evidence exists, OC trip is weighed against "
                    "Breaker-failure / Intertrip hypotheses before calling feeder root cause."
                ),
                "causal_chain": [
                    c
                    for c in (
                        f"Fault classification: {fault.status} ({ft or 'UNKNOWN'})",
                        oc_ph.title() if oc_ph else None,
                        ef_ph.title() if ef_ph else None,
                        dir_ph.title() if dir_ph else None,
                        "Intertrip / cascade markers present — not OC-only story"
                        if (
                            "intertrip_signal_observed" in bag
                            or "cascade_lbb_detected" in bag
                        )
                        else None,
                        f"Consistency summary: {consistency.summary_status}",
                    )
                    if c
                ],
                "recommended_actions": actions or ["Engineer review of primary evidence"],
            }

        if hid == "TRANSFORMER_INTERNAL_FAULT":
            tf_ok = "through_fault_excluded" in bag
            if "transformer_diff_operated" in bag or "differential_operated" in bag:
                xfmr_ev = "transformer differential (87T/87RGF) trip"
            elif "transformer_diff_picked_up" in bag:
                xfmr_ev = "transformer differential (87T/87RGF) pickup"
            else:
                xfmr_ev = None
            return {
                "statement": (
                    f"{title} is {status}"
                    + (
                        f" based on {xfmr_ev}"
                        + (
                            " with Id/Ir through-fault exclusion."
                            if tf_ok
                            else "."
                        )
                        if xfmr_ev
                        else " — transformer differential evidence is incomplete."
                    )
                ),
                "explanation": (
                    "Requires 87T/87RGF evidence; CONFIRMED needs Id/Ir through-fault exclusion. "
                    "Not inferred from OC/distance alone."
                ),
                "causal_chain": supporting[:6],
                "recommended_actions": (
                    [
                        "Confirm transformer asset / winding inspection",
                        "Archive Id/Ir operate–restraint evidence",
                    ]
                    if tf_ok
                    else [
                        "Supply HV/LV winding currents (or multi-end phasors) for Id/Ir",
                        "Review 87T operate/restraint and exclude through-fault / CT sat",
                    ]
                ),
            }

        if hid == "BUS_ZONE_FAULT":
            return {
                "statement": (
                    f"{title} is {status}"
                    + (
                        " based on bus differential (87B) operation."
                        if "bus_diff_operated" in bag
                        else " — bus differential evidence is incomplete."
                    )
                ),
                "explanation": "Bus-zone hypothesis — boosted only when 87B operated.",
                "causal_chain": supporting[:6],
                "recommended_actions": [
                    "Review 87B zone / CT wiring and check zone selectivity",
                    "Confirm busbar inspection / lockout (86) status",
                ],
            }

        if hid == "GENERATOR_INTERNAL_FAULT":
            return {
                "statement": (
                    f"{title} is {status}"
                    + (
                        " based on generator differential (87G) operation."
                        if "generator_diff_operated" in bag
                        else " — generator differential evidence is incomplete."
                    )
                ),
                "explanation": "Generator-zone hypothesis — boosted only when 87G operated.",
                "causal_chain": supporting[:6],
                "recommended_actions": [
                    "Review 87G operate/restraint and unit protection scheme",
                    "Confirm generator / unit breaker status",
                ],
            }

        if hid == "BREAKER_FAILURE":
            oc_ph = _family_assert_phrase(asses, _FAMILY_OVERCURRENT)
            bf_ph = _family_assert_phrase(asses, _FAMILY_BREAKER_FAILURE)
            if "cascade_lbb_detected" in bag:
                detail = (
                    " — local breaker failed to open after a valid trip; "
                    "50BF (Breaker failure) / LBB sent intertrip and the upstream bay cleared. "
                    "Upstream trip is a cascade consequence, not the initiating cause. "
                    "Local 50/51 (overcurrent) trip alone is not the root cause when BF + intertrip follow."
                )
                expl = (
                    "Step-by-step LBB cascade: (1) fault current / waveforms, (2) local 50/51 trip "
                    "command, (3) breaker fails to interrupt (current persists), (4) 50BF/LBB + intertrip "
                    "send, (5) upstream clearance. Primary root cause = local breaker failure."
                )
                actions = [
                    "Inspect / maintain the failed local breaker before re-energizing",
                    "Confirm LBB timer and intertrip path (GOOSE / wired TT) operated as designed",
                    "Do not treat upstream HV trip or local 50/51 alone as the primary root cause",
                ]
                chain = [
                    c
                    for c in (
                        f"Fault classification: {fault.status} ({ft or 'UNKNOWN'})",
                        "Waveforms / electrical: fault current and persist into BF window"
                        if "current_persists" in bag or "current_increase_observed" in bag
                        else None,
                        oc_ph or ("Local overcurrent (50/51) trip asserted" if "overcurrent_element_operated" in bag else None),
                        "Trip command issued — breaker did not clear",
                        bf_ph or "50BF (Breaker failure) / LBB logic satisfied",
                        "Intertrip / transfer-trip sent upstream"
                        if "intertrip_signal_observed" in bag or "intertrip_send_observed" in bag
                        else None,
                        "Upstream / backup bay cleared (cascade consequence)"
                        if "cascade_upstream_clearance" in bag
                        else None,
                        f"Consistency summary: {consistency.summary_status}",
                    )
                    if c
                ]
            else:
                detail = (
                    " based on 50BF (Breaker failure) logic evidence."
                    if "bf_logic_satisfied" in bag
                    else " — breaker-failure evidence is incomplete."
                )
                expl = (
                    "Step check: trip command → current persists → 50BF operate. "
                    "Requires BF element plus trip/current-persist evidence when available."
                )
                actions = [
                    "Verify trip issued and current persisted into BF window",
                    "Confirm adjacent breaker trips / BF lockout",
                ]
                chain = [
                    c
                    for c in (
                        f"Fault classification: {fault.status} ({ft or 'UNKNOWN'})",
                        oc_ph,
                        bf_ph or ("50BF (Breaker failure) operated" if "bf_logic_satisfied" in bag else None),
                        "Current persisted after trip command"
                        if "current_persists" in bag
                        else None,
                        f"Consistency summary: {consistency.summary_status}",
                    )
                    if c
                ] or supporting[:6]
            return {
                "statement": f"{title} is {status}{detail}",
                "explanation": expl,
                "causal_chain": chain,
                "recommended_actions": actions,
            }

        if hid == "EXTERNAL_GRID_DISTURBANCE":
            return {
                "statement": (
                    f"{title} is {status}"
                    + (
                        " based on voltage/frequency element operation."
                        if "voltage_element_operated" in bag or "frequency_element_operated" in bag
                        else " from limited system-disturbance evidence."
                    )
                ),
                "explanation": "Favoured when 27/59/81 operated without a clear shunt-fault clearance scheme.",
                "causal_chain": supporting[:6],
                "recommended_actions": [
                    "Correlate with grid events / neighbouring stations",
                    "Review voltage and frequency element settings",
                ],
            }

        if hid == "MOTOR_START":
            pu_only = (
                "protection_pickup_asserted" in bag
                or (
                    (
                        "overcurrent_element_operated" in bag
                        or "motor_element_operated" in bag
                    )
                    and "protection_operated" not in bag
                )
            )
            detail = " — motor-protection / starting-current signature"
            if pu_only:
                detail += " (pickup without trip)."
            else:
                detail += "."
            return {
                "statement": f"{title} is {status}{detail}",
                "explanation": (
                    "Motor start path when Start/Thermal/Stall digitals or START-bay "
                    "prefixes are present with OC/46 pickup and no trip. Not a feeder "
                    "shunt-fault default."
                ),
                "causal_chain": supporting[:6],
                "recommended_actions": [
                    "Confirm motor start / process sequence with SOE or ops log",
                    "Review start supervision (48), thermal (49), and NPS (46) settings",
                    "Do not treat starting current as a feeder AB/ABC fault",
                ],
            }

        if hid == "SWITCH_ONTO_FAULT":
            bits: list[str] = []
            if "sotf_element_asserted" in bag:
                bits.append("SOTF digital / element asserted")
            if "breaker_close_observed" in bag:
                bits.append("pre-trip breaker close observed")
            elif "autoreclose_issued" in bag:
                bits.append("autoreclose reclaim present (not used as SOTF close)")
            if "fault_classified" in bag:
                bits.append(f"COMTRADE fault classified ({fault_bit})")
            if "protection_operated" in bag:
                bits.append(_protection_assert_phrase(bag) or "protection trip asserted")
            detail = (" — " + "; ".join(bits) + ".") if bits else "."
            return {
                "statement": f"{title} is {status}{detail}",
                "explanation": (
                    "Switch-onto-fault (SOTF): breaker close / energize into a shunt fault "
                    "with protection trip. Distinct from magnetizing inrush / energization "
                    "(pickup without trip) and from motor starting current."
                ),
                "causal_chain": supporting[:6],
                "recommended_actions": [
                    "Confirm close / energize sequence vs fault inception on SOE / 52a",
                    "Review SOTF / instantaneous OC enable on close (if used)",
                    "Correlate pre-existing fault or close-into-fault conditions",
                ],
            }

        if hid == "SWITCHING_TRANSIENT":
            inrush = "magnetizing_inrush_possible" in bag
            diff_pu = (
                "transformer_diff_picked_up" in bag
                or "line_diff_picked_up" in bag
                or "bus_diff_picked_up" in bag
                or "generator_diff_picked_up" in bag
            ) and "differential_operated" not in bag and "transformer_diff_operated" not in bag
            oc_pu = (
                "overcurrent_element_picked_up" in bag
                or "earth_fault_element_picked_up" in bag
                or (
                    (
                        "overcurrent_element_operated" in bag
                        or "earth_fault_element_operated" in bag
                    )
                    and "protection_operated" not in bag
                )
            )
            if inrush and diff_pu:
                detail = (
                    " — magnetizing inrush / transformer charging signature (elevated H2); "
                    "87 pickup without trip is consistent with restrained energization."
                )
                actions = [
                    "Confirm transformer energization / charging sequence with SOE",
                    "Verify 87 harmonic restraint / inrush blocking settings",
                    "Do not treat 87 pickup-only as internal fault without trip + Id/Ir",
                ]
                expl = (
                    "Energization / inrush path when H2 is elevated and 87 picks up without trip; "
                    "also boosted for 68/78 (/79). Not a shunt-fault default."
                )
            elif inrush and oc_pu:
                detail = (
                    " — magnetizing inrush / transformer charging signature (elevated H2); "
                    "overcurrent pickup without trip."
                )
                actions = [
                    "Confirm transformer energization / charging sequence with SOE",
                    "Review OC pickup vs inrush / charging current",
                ]
                expl = (
                    "Energization / inrush from elevated H2; protection digitals show OC/EF "
                    "pickup without trip."
                )
            elif inrush:
                detail = (
                    " — magnetizing inrush / transformer charging signature (elevated H2)."
                )
                actions = [
                    "Confirm transformer energization / charging sequence with SOE",
                    "Correlate with switching / charging schedule",
                ]
                expl = "Energization / inrush from elevated H2; not a shunt-fault default."
            else:
                detail = " from switching / power-swing related evidence."
                actions = [
                    "Correlate with switching schedule / SOE",
                    "Review power-swing blocking / out-of-step logic",
                ]
                expl = (
                    "Boosted for 68/78 (/79) / correlated switching. Not a shunt-fault default."
                )
            return {
                "statement": f"{title} is {status}{detail}",
                "explanation": expl,
                "causal_chain": supporting[:6],
                "recommended_actions": actions,
            }

        if hid == "LIGHTNING":
            has = "lightning_evidence" in bag
            return {
                "statement": (
                    f"{title} is {status}"
                    + (
                        " — strike / storm evidence is present for this circuit disturbance."
                        if has
                        else " — awaiting lightning CSV or engineer field confirmation (not inferred from waveform alone)."
                    )
                ),
                "explanation": (
                    "Physical cause for line/feeder zones only; requires structured lightning evidence."
                ),
                "causal_chain": supporting[:6] or (
                    ["cause_specific_evidence_absent"] if not has else []
                ),
                "recommended_actions": [
                    "Attach lightning strike correlation or mark lightning evidence on RCA",
                    "Confirm overhead circuit exposure / storm report",
                    "Re-run analysis after enrichment",
                ],
            }

        if hid == "VEGETATION":
            has = "field_report_vegetation" in bag
            return {
                "statement": (
                    f"{title} is {status}"
                    + (
                        " — field report confirms vegetation / tree contact."
                        if has
                        else " — awaiting field confirmation (not inferred from COMTRADE alone)."
                    )
                ),
                "explanation": "Line/feeder cause; requires field_report_vegetation token.",
                "causal_chain": supporting[:6] or (
                    ["cause_specific_evidence_absent"] if not has else []
                ),
                "recommended_actions": [
                    "Confirm vegetation contact from patrol / LiDAR / field notes",
                    "Mark vegetation evidence on RCA and re-run analysis",
                ],
            }

        if hid == "INSULATION_FLASHOVER":
            has = "insulation_evidence" in bag
            return {
                "statement": (
                    f"{title} is {status}"
                    + (
                        " — insulation / pollution flashover evidence is recorded."
                        if has
                        else " — awaiting insulation inspection evidence."
                    )
                ),
                "explanation": "Requires insulation_evidence; not invented from fault type alone.",
                "causal_chain": supporting[:6],
                "recommended_actions": [
                    "Record insulator / bushing inspection findings",
                    "Mark insulation evidence on RCA and re-run analysis",
                ],
            }

        if hid == "CABLE_FAULT":
            has = "cable_asset_confirmed" in bag
            return {
                "statement": (
                    f"{title} is {status}"
                    + (
                        " — cable / underground asset is confirmed for this circuit."
                        if has
                        else " — awaiting cable asset confirmation from registry or engineer tag."
                    )
                ),
                "explanation": "Requires cable_asset_confirmed (asset type CABLE or engineer tag).",
                "causal_chain": supporting[:6],
                "recommended_actions": [
                    "Confirm UG cable section in asset registry",
                    "Tag cable asset on RCA if plant data is missing",
                ],
            }

        if hid == "COMMUNICATION_FAILURE":
            return {
                "statement": (
                    f"{title} is {status}"
                    + (
                        " — pilot/COMM channel evidence is present."
                        if "comm_channel_evidence" in bag
                        else " — pilot scheme suspected but COMM digital evidence incomplete."
                    )
                ),
                "explanation": "Relevant for POTT/pilot / 87L schemes; evidence-gated.",
                "causal_chain": supporting[:6],
                "recommended_actions": [
                    "Verify carrier / fibre / GOOSE channel status at the event time",
                    "Map COMM digitals on DR targets and re-run analysis",
                ],
            }

        if hid == "INTERTRIP_OPERATION":
            oc_ph = _family_assert_phrase(asses, _FAMILY_OVERCURRENT)
            if (
                "intertrip_receive_observed" in bag
                or "cascade_upstream_clearance" in bag
            ):
                detail = (
                    " — this bay received LBB / transfer-trip (intertrip) and cleared as "
                    "upstream backup. Local 50/51 (overcurrent) digitals here are clearance "
                    "consequence, not the initiating feeder root cause. Correlate with the "
                    "initiator (LV) event for breaker-failure primary RCA."
                )
                expl = (
                    "Step-by-step: (1) waveforms show clearance at this end, (2) digital "
                    "intertrip RX / transfer-trip asserted, (3) local trip follows intertrip — "
                    "not a standalone feeder fault. Primary plant root cause is usually "
                    "downstream breaker failure on the initiator end."
                )
                actions = [
                    "Open the initiator (LV) event for breaker-failure / LBB primary RCA",
                    "Confirm intertrip RX digital mapping and timing vs remote BF send",
                    "Do not treat local 50/51 trip alone as feeder fault root cause when intertrip RX is present",
                ]
                chain = [
                    c
                    for c in (
                        "Digital: intertrip / transfer-trip receive asserted",
                        oc_ph
                        or (
                            "Local overcurrent (50/51) also asserted — treated as clearance consequence"
                            if "overcurrent_element_operated" in bag
                            else None
                        ),
                        "SOE / timeline: clearance after intertrip (not initiating BF)",
                        "Upstream / backup role — not initiating bay",
                        f"Fault classification at this end: {fault.status} ({ft or 'UNKNOWN'})",
                        f"Consistency summary: {consistency.summary_status}",
                    )
                    if c
                ]
            elif "intertrip_signal_observed" in bag:
                detail = " — intertrip / transfer-trip digital observed."
                expl = (
                    "Intertrip digital present — correlate with SOE and remote-end BF before "
                    "calling a local feeder OC root cause."
                )
                actions = [
                    "Confirm TT / intertrip channel mapping on DR targets",
                    "Correlate remote-end trip timing",
                ]
                chain = [
                    c
                    for c in (
                        "Digital: intertrip / transfer-trip observed",
                        oc_ph,
                        f"Fault classification: {fault.status} ({ft or 'UNKNOWN'})",
                    )
                    if c
                ] or supporting[:6]
            else:
                detail = " — awaiting intertrip digital evidence."
                expl = "Requires intertrip_signal_observed from DR / SOE."
                actions = [
                    "Confirm TT / intertrip channel mapping on DR targets",
                    "Correlate remote-end trip timing",
                ]
                chain = supporting[:6]
            return {
                "statement": f"{title} is {status}{detail}",
                "explanation": expl,
                "causal_chain": chain,
                "recommended_actions": actions,
            }

        if hid in FAULT_SIDE_HYPOTHESES and hid not in (
            "EXTERNAL_LINE_FAULT",
            "INTERNAL_FEEDER_FAULT",
            "TRANSFORMER_INTERNAL_FAULT",
            "BUS_ZONE_FAULT",
            "GENERATOR_INTERNAL_FAULT",
            "LIGHTNING",
            "VEGETATION",
            "INSULATION_FLASHOVER",
            "CABLE_FAULT",
            "EXTERNAL_GRID_DISTURBANCE",
            "SWITCHING_TRANSIENT",
            "SWITCH_ONTO_FAULT",
            "MOTOR_START",
        ):
            parts = []
            if "fault_classified" in bag:
                parts.append(f"COMTRADE indicates a {fault_bit}")
            _prot = _protection_assert_phrase(bag)
            if _prot:
                parts.append(_prot)
            if "protection_operated_consistently" in bag:
                parts.append("operate also consistent with settings")
            statement = (
                f"{title} is {status} based on: " + "; ".join(parts) + "."
                if parts
                else f"{title} ranked {status} from available analysis fields."
            )
            _prot_title = (
                "Protection pickup with trip"
                if "protection_pickup_with_trip" in bag
                else (
                    "Protection pickup asserted"
                    if "protection_pickup_asserted" in bag
                    else (
                        "Protection trip asserted"
                        if (
                            "protection_trip_asserted" in bag
                            or "protection_operated" in bag
                        )
                        else (
                            "Protection response observed"
                            if "protection_responded" in bag
                            else None
                        )
                    )
                )
            )
            return {
                "statement": statement,
                "explanation": (
                    "Ranked from electrical classification, protection assessments, "
                    "and consistency — scheme-aware."
                ),
                "causal_chain": [
                    c
                    for c in (
                        f"Fault classification: {fault.status} ({ft or 'UNKNOWN'})",
                        _prot_title,
                        f"Consistency summary: {consistency.summary_status}",
                    )
                    if c
                ],
                "recommended_actions": [
                    a
                    for a in (
                        "Confirm faulted circuit findings in the field",
                        "Confirm breaker opened and fault cleared"
                        if "trip_observed" in bag
                        else None,
                        f"Obtain: {', '.join(missing[:3])}" if missing else None,
                    )
                    if a
                ]
                or ["Engineer review of primary evidence"],
            }

        if hid == "RELAY_MISOPERATION":
            statement = (
                f"Relay misoperation is {status}. "
                + (
                    "A classified electrical fault contradicts pure misoperation."
                    if "fault_classified" in bag
                    else "Requires verified settings and no-fault electrical evidence."
                )
            )
            return {
                "statement": statement,
                "explanation": "Misoperation is never confirmed from inconsistency alone.",
                "causal_chain": supporting[:5],
                "recommended_actions": [
                    "Verify active setting group",
                    "Compare expected vs actual element operation",
                ],
            }

        if hid == "UNKNOWN":
            return {
                "statement": (
                    f"Cause remains {status} — available evidence does not uniquely "
                    "identify a root cause."
                ),
                "explanation": "Fallback hypothesis when competing explanations are weak.",
                "causal_chain": [],
                "recommended_actions": [
                    "Collect additional SOE / settings / field report"
                ],
            }

        return {
            "statement": (
                f"{title} is {status} "
                f"(supporting={len(supporting)}, missing={len(missing)})."
            ),
            "explanation": "Scored from structured evidence bag only.",
            "causal_chain": supporting[:6],
            "recommended_actions": (
                [f"Seek missing evidence: {m}" for m in missing[:3]]
                or ["Review supporting evidence list"]
            ),
        }
