"""Hypothesis-based RCA engine (deterministic, evidence-gated)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from app.core.enums import HypothesisStatus
from common.rules_path import load_yaml, resolve_rules_root
from consistency.engine import ConsistencyResult
from fault_analysis import FaultClassificationResult
from protection.models import ProtectionAssessment


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


def _assessment_operated(assessment: ProtectionAssessment) -> bool:
    return (
        assessment.pickup is True
        or assessment.trip is True
        or assessment.actual_operation == "OPERATED"
    )


def _active_protection_zones(bag: set[str]) -> frozenset[str]:
    """Infer which protection zones are active from operated-element evidence tokens."""
    zones: set[str] = set()
    if "distance_element_operated" in bag or "line_diff_operated" in bag:
        zones.add("line")
    if (
        "overcurrent_element_operated" in bag or "earth_fault_element_operated" in bag
    ) and "transformer_diff_operated" not in bag and "bus_diff_operated" not in bag and "generator_diff_operated" not in bag and "line_diff_operated" not in bag:
        # OC/EF alone → feeder/local; 87RGF also sets earth_fault but usually with xfmr
        if "distance_element_operated" not in bag:
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

    return "open"


def _scheme_tokens_from_assessments(assessments: list[ProtectionAssessment]) -> set[str]:
    """Map operated (or consistently assessed) elements to scheme evidence tokens."""
    tokens: set[str] = set()
    for a in assessments:
        code = _element_code(a)
        if not code:
            continue
        operated = _assessment_operated(a)

        def _mark(present: str, operated_tok: str, scheme: str) -> None:
            tokens.add(present)
            if operated:
                tokens.add(operated_tok)
                tokens.add(scheme)

        if code in _FAMILY_DISTANCE:
            _mark("scheme_distance_present", "distance_element_operated", "scheme_distance")
        if code in _FAMILY_OVERCURRENT:
            _mark("scheme_overcurrent_present", "overcurrent_element_operated", "scheme_overcurrent")
        if code in _FAMILY_EARTH_FAULT:
            _mark("scheme_earth_fault_present", "earth_fault_element_operated", "scheme_earth_fault")
        if code in _FAMILY_LINE_DIFF:
            _mark("scheme_line_diff_present", "line_diff_operated", "scheme_line_diff")
            if operated:
                tokens.add("differential_operated")
                tokens.add("scheme_differential")
        if code in _FAMILY_XFMR_DIFF:
            _mark("scheme_xfmr_diff_present", "transformer_diff_operated", "scheme_xfmr_diff")
            if operated:
                tokens.add("differential_operated")
                tokens.add("scheme_differential")
        if code in _FAMILY_BUS_DIFF:
            _mark("scheme_bus_diff_present", "bus_diff_operated", "scheme_bus_diff")
            if operated:
                tokens.add("differential_operated")
                tokens.add("scheme_differential")
        if code in _FAMILY_GEN_DIFF:
            _mark("scheme_gen_diff_present", "generator_diff_operated", "scheme_gen_diff")
            if operated:
                tokens.add("differential_operated")
                tokens.add("scheme_differential")
        if code in _FAMILY_BREAKER_FAILURE:
            _mark("scheme_breaker_failure_present", "bf_logic_satisfied", "scheme_breaker_failure")
        if code in _FAMILY_DIRECTIONAL:
            _mark("scheme_directional_present", "directional_element_operated", "scheme_directional")
        if code in _FAMILY_VOLTAGE:
            _mark("scheme_voltage_present", "voltage_element_operated", "scheme_voltage")
        if code in _FAMILY_FREQUENCY:
            _mark("scheme_frequency_present", "frequency_element_operated", "scheme_frequency")
        if code in _FAMILY_POWER_SWING:
            _mark("scheme_power_swing_present", "power_swing_element_operated", "scheme_power_swing")
        if code in _FAMILY_RECLOSE_LOCKOUT:
            _mark("scheme_reclose_present", "reclose_or_lockout_operated", "scheme_reclose")
        if code in _FAMILY_SYNC:
            _mark("scheme_sync_present", "sync_element_operated", "scheme_sync")
        if code in _FAMILY_POWER:
            _mark("scheme_power_present", "power_unbalance_operated", "scheme_power")
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

    def to_dict(self) -> dict[str, Any]:
        return {
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "weights": self.weights,
            "primary": self.primary.to_dict() if self.primary else None,
            "limitations": self.limitations,
            "forced_inconclusive": self.forced_inconclusive,
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
        "SWITCHING_TRANSIENT": "Switching transient",
        "RELAY_MISOPERATION": "Relay misoperation",
        "PROTECTION_SETTING_ERROR": "Protection setting error",
        "RELAY_CONFIGURATION_ERROR": "Relay configuration error",
        "BREAKER_FAILURE": "Breaker failure",
        "CT_SATURATION": "CT saturation",
        "VT_CVT_ABNORMALITY": "VT / CVT abnormality",
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
    ) -> RCAResult:
        electrical_flags = dict(electrical_flags or {})
        ml_supports = ml_supports or {}
        similarity_supports = similarity_supports or {}

        # Derive flags from fault when timeline did not flag them
        if fault.status in ("CLASSIFIED", "PROBABLE"):
            electrical_flags.setdefault("fault_indicated", True)
            feat = fault.evidence if isinstance(fault.evidence, dict) else {}
            if feat.get("available") and any(
                feat.get(k)
                for k in ("Ia_elevated", "Ib_elevated", "Ic_elevated", "ground")
            ):
                electrical_flags.setdefault("current_increase", True)

        result = RCAResult(weights=dict(self.weights))
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
                hid, status, fault, supporting, missing, evidence_bag, consistency
            )

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
        return top

    def _collect_evidence(
        self,
        fault: FaultClassificationResult,
        assessments: list[ProtectionAssessment],
        consistency: ConsistencyResult,
        electrical_flags: dict[str, Any],
    ) -> set[str]:
        bag: set[str] = set()
        if fault.status in ("CLASSIFIED", "PROBABLE"):
            bag.add("fault_classified")
            bag.add(f"fault_type_{fault.fault_type}")
        if fault.status == "CLASSIFIED":
            bag.add("fault_classified_strong")

        any_trip = any(a.trip is True for a in assessments)
        any_pickup = any(a.pickup is True for a in assessments)
        if any_trip:
            bag.add("trip_observed")
        if any_pickup or any_trip:
            bag.add("protection_responded")
        if any(
            a.consistency == "CONSISTENT" and a.actual_operation == "OPERATED"
            for a in assessments
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

        if consistency.has_critical_setting_inconsistency:
            bag.add("setting_inconsistency_unverified")
        elif consistency.summary_status == "CONSISTENT":
            bag.add("settings_behavior_consistent")
            bag.add("settings_partial")
        else:
            bag.add("settings_partial")

        bag |= _scheme_tokens_from_assessments(assessments)

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
            for tok in ("power_swing_element_operated", "scheme_power_swing", "reclose_or_lockout_operated"):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "BREAKER_FAILURE":
            for tok in ("bf_logic_satisfied", "scheme_breaker_failure", "current_persists", "trip_command_observed"):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        if hid == "RELAY_MISOPERATION":
            for tok in ("trip_observed", "electrical_no_fault"):
                if tok in bag and tok not in supporting:
                    extras.append(tok)
        supporting = supporting + extras

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
        if hid == "INTERNAL_FEEDER_FAULT":
            if "distance_element_operated" in bag and "overcurrent_element_operated" not in bag:
                contradicting.append("distance_primary_without_oc")
            if "differential_operated" in bag and "earth_fault_element_operated" not in bag:
                # 87RGF counts as EF; other diffs should not pick feeder
                if "transformer_diff_operated" in bag or "bus_diff_operated" in bag or "generator_diff_operated" in bag or "line_diff_operated" in bag:
                    contradicting.append("differential_scheme_operated")
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
        if "protection_operated_consistently" in bag:
            score += 0.15
        elif "protection_responded" in bag:
            score += 0.08
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
            if "earth_fault_element_operated" in bag:
                score += 0.18
            if "directional_element_operated" in bag:
                score += 0.08
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
            if "transformer_diff_operated" in bag:
                return 0.82 if "fault_classified" in bag else 0.60
            if "differential_operated" in bag and "bus_diff_operated" not in bag and "line_diff_operated" not in bag and "generator_diff_operated" not in bag:
                return 0.55
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
            return min(score, 1.0)

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
            return min(score, 1.0)
        if hid == "PROTECTION_SETTING_ERROR":
            return 0.55 if "setting_inconsistency_unverified" in bag else 0.2
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
    ) -> dict[str, Any]:
        ft = fault.fault_type if fault.fault_type and fault.fault_type != "UNKNOWN" else None
        fault_bit = f"{ft} fault" if ft else "disturbance"
        title = _title(hid)

        if hid == "EXTERNAL_LINE_FAULT":
            parts = []
            if "fault_classified" in bag:
                parts.append(f"COMTRADE indicates a {fault_bit}")
            if "distance_element_operated" in bag:
                parts.append("distance element (21) operated")
            if "line_diff_operated" in bag:
                parts.append("line differential (87L) operated")
            if "distance_estimate_available" in bag:
                parts.append("a location estimate is available")
            if "current_increase_observed" in bag:
                parts.append("elevated phase/ground current observed")
            if "protection_operated_consistently" in bag:
                parts.append("protection operated consistently with settings")
            elif "protection_responded" in bag:
                parts.append("protection pickup/trip asserted")
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
                        "Distance element operated"
                        if "distance_element_operated" in bag
                        else None,
                        "Line differential operated" if "line_diff_operated" in bag else None,
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
            if "overcurrent_element_operated" in bag:
                parts.append("overcurrent element (50/51) operated")
            if "earth_fault_element_operated" in bag:
                parts.append("earth-fault element (50N/51N/67N) operated")
            if "directional_element_operated" in bag:
                parts.append("directional element (67) operated")
            if "current_increase_observed" in bag:
                parts.append("elevated phase/ground current observed")
            if "protection_operated_consistently" in bag:
                parts.append("protection operated consistently with settings")
            elif "protection_responded" in bag:
                parts.append("protection pickup/trip asserted")
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
                    "Feeder / local-circuit hypothesis — boosted for 50/51/EF/67; "
                    "demoted when distance or unit differential is primary."
                ),
                "causal_chain": [
                    c
                    for c in (
                        f"Fault classification: {fault.status} ({ft or 'UNKNOWN'})",
                        "Overcurrent element operated"
                        if "overcurrent_element_operated" in bag
                        else None,
                        "Earth-fault element operated"
                        if "earth_fault_element_operated" in bag
                        else None,
                        "Directional element operated"
                        if "directional_element_operated" in bag
                        else None,
                        f"Consistency summary: {consistency.summary_status}",
                    )
                    if c
                ],
                "recommended_actions": actions or ["Engineer review of primary evidence"],
            }

        if hid == "TRANSFORMER_INTERNAL_FAULT":
            return {
                "statement": (
                    f"{title} is {status}"
                    + (
                        " based on transformer differential (87T/87RGF) operation."
                        if "transformer_diff_operated" in bag or "differential_operated" in bag
                        else " — transformer differential evidence is incomplete."
                    )
                ),
                "explanation": "Requires 87T/87RGF evidence; not inferred from OC/distance alone.",
                "causal_chain": supporting[:6],
                "recommended_actions": [
                    "Review 87T operate/restraint and through-fault exclusion",
                    "Confirm transformer asset and winding currents",
                ],
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
            return {
                "statement": (
                    f"{title} is {status}"
                    + (
                        " based on 50BF / breaker-failure logic evidence."
                        if "bf_logic_satisfied" in bag
                        else " — breaker-failure evidence is incomplete."
                    )
                ),
                "explanation": "Requires BF element operation plus trip/current-persist evidence when available.",
                "causal_chain": supporting[:6],
                "recommended_actions": [
                    "Verify trip issued and current persisted into BF window",
                    "Confirm adjacent breaker trips / BF lockout",
                ],
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

        if hid == "SWITCHING_TRANSIENT":
            return {
                "statement": f"{title} is {status} from switching / power-swing related evidence.",
                "explanation": "Boosted for 68/78 (/79) evidence; not a shunt-fault default.",
                "causal_chain": supporting[:6],
                "recommended_actions": [
                    "Correlate with switching schedule / SOE",
                    "Review power-swing blocking / out-of-step logic",
                ],
            }

        if hid in ("CABLE_FAULT",) or (
            hid in FAULT_SIDE_HYPOTHESES
            and hid
            not in (
                "EXTERNAL_LINE_FAULT",
                "INTERNAL_FEEDER_FAULT",
                "TRANSFORMER_INTERNAL_FAULT",
                "BUS_ZONE_FAULT",
                "GENERATOR_INTERNAL_FAULT",
                "EXTERNAL_GRID_DISTURBANCE",
                "SWITCHING_TRANSIENT",
            )
        ):
            parts = []
            if "fault_classified" in bag:
                parts.append(f"COMTRADE indicates a {fault_bit}")
            if "protection_operated_consistently" in bag:
                parts.append("protection operated consistently with settings")
            elif "protection_responded" in bag:
                parts.append("protection pickup/trip asserted")
            statement = (
                f"{title} is {status} based on: " + "; ".join(parts) + "."
                if parts
                else f"{title} ranked {status} from available analysis fields."
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
                        "Protection response observed"
                        if "protection_responded" in bag
                        else None,
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
