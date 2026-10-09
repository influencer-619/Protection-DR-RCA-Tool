"""Executable RCA scenario matrix (L1/L2/L3 + LBB) — thin adapter for HypothesisEngine.

Loads ``rules/rca/matrix_v1.yaml``. Does not fork a second RCA engine: matching
produces compound class, LBB step checklist, traces, and optional demotions that
the existing HypothesisEngine applies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from common.rules_path import load_yaml, resolve_rules_root


@dataclass
class LbbStepResult:
    id: int
    label: str
    status: str  # PASS | FAIL | UNKNOWN
    evidence: list[str] = field(default_factory=list)
    note: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class MatrixMatchResult:
    matrix_version: str
    matched_scenario_id: Optional[str] = None
    matched_title: Optional[str] = None
    compound_class: Optional[str] = None
    primary_hypothesis: Optional[str] = None
    fallback_hypothesis: Optional[str] = None
    traces: list[str] = field(default_factory=list)
    lbb_steps: list[LbbStepResult] = field(default_factory=list)
    lbb_steps_passed: int = 0
    lbb_steps_total: int = 0
    guardrail_actions: list[dict[str, Any]] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    # Excel ladder: which of L1/L2/L3 contributed evidence to the match
    level_coverage: dict[str, Any] = field(default_factory=dict)
    prefer_primary: bool = False

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["lbb_steps"] = [s.to_dict() if hasattr(s, "to_dict") else s for s in self.lbb_steps]
        return d


# Token → Excel layer (L1 digitals / L2 SOE-sequence / L3 DR analogues)
_LAYER_L1 = frozenset(
    {
        "protection_operated",
        "trip_observed",
        "protection_pickup_with_trip",
        "protection_pickup_asserted",
        "protection_trip_asserted",
        "overcurrent_element_operated",
        "earth_fault_element_operated",
        "distance_element_operated",
        "differential_operated",
        "transformer_diff_operated",
        "bus_diff_operated",
        "generator_diff_operated",
        "line_diff_operated",
        "bf_element_operated",
        "bf_logic_satisfied",
        "sotf_element_asserted",
        "scheme_overcurrent",
        "scheme_earth_fault",
        "scheme_distance",
        "scheme_breaker_failure",
        "intertrip_send_observed",
        "intertrip_receive_observed",
        "intertrip_signal_observed",
        "unbalance_protection_operated",
    }
)
_LAYER_L2 = frozenset(
    {
        "breaker_open_confirmed",
        "successful_clearing",
        "breaker_close_observed",
        "cascade_lbb_detected",
        "cascade_upstream_clearance",
        "fault_inception_observed",
        "switching_event_correlated",
        "autoreclose_issued",
        "autoreclose_success",
        "autoreclose_fail",
        "reclose_successful",
        "reclose_unsuccessful",
        "external_event_correlated",
        "comm_channel_evidence",
        "l2_sequence_present",
        "l2_causality_ok",
        "l2_causality_weak",
        "l2_inception_before_trip",
        "l2_intertrip_in_sequence",
        "l2_reclose_after_trip",
    }
)
_LAYER_L3 = frozenset(
    {
        "fault_classified",
        "fault_classified_strong",
        "current_increase_observed",
        "current_persists",
        "ground_involved",
        "negative_sequence_elevated",
        "zero_sequence_elevated",
        "voltage_sag_observed",
        "waveform_distortion",
        "harmonic_evidence",
        "magnetizing_inrush_possible",
        "motor_start_possible",
        "ct_saturation_suspected",
        "electrical_no_fault",
        "dfr_non_fault_event",
        "distance_estimate_available",
        "loop_impedance_available",
        "through_fault_excluded",
        "l3_fallback_applied",
        "earth_fault_l3_inferred",
        "distance_l3_inferred",
        "overcurrent_l3_inferred",
        "unbalance_l3_inferred",
        "differential_l3_inferred",
        "sotf_l3_inferred",
        "bf_l3_inferred",
        "inrush_l3_inferred",
        "motor_start_l3_inferred",
    }
)


def layer_tokens_present(bag: set[str]) -> dict[str, bool]:
    """Which Excel layers have at least one evidence token in the bag."""
    return {
        "L1": bool(bag & _LAYER_L1),
        "L2": bool(bag & _LAYER_L2),
        "L3": bool(bag & _LAYER_L3),
    }


def _level_coverage_for_match(
    bag: set[str], hit_tokens: list[str]
) -> dict[str, Any]:
    """Per-match ladder: which layers contributed to the scenario hit tokens."""
    hits = set(hit_tokens)
    cov = {
        "L1": bool(hits & _LAYER_L1),
        "L2": bool(hits & _LAYER_L2),
        "L3": bool(hits & _LAYER_L3),
    }
    agree = sum(1 for v in cov.values() if v)
    cov["agree_count"] = agree
    cov["bag_layers"] = layer_tokens_present(bag)
    cov["ladder"] = "→".join(k for k in ("L1", "L2", "L3") if cov[k]) or "NONE"
    return cov


def _matrix_path() -> Path:
    return resolve_rules_root() / "rca" / "matrix_v1.yaml"


@lru_cache(maxsize=1)
def load_matrix() -> dict[str, Any]:
    path = _matrix_path()
    if not path.is_file():
        return {"version": "missing", "scenarios": [], "lbb_steps": [], "guardrails": []}
    data = load_yaml(path)
    return data if isinstance(data, dict) else {"version": "invalid", "scenarios": []}


def reload_matrix() -> dict[str, Any]:
    load_matrix.cache_clear()
    return load_matrix()


def _has_any(bag: set[str], tokens: list[str] | None) -> bool:
    if not tokens:
        return False
    from rca.ladder import token_satisfied

    return any(token_satisfied(bag, t) for t in tokens)


def _has_all(bag: set[str], tokens: list[str] | None) -> bool:
    if not tokens:
        return True
    from rca.ladder import token_satisfied

    return all(token_satisfied(bag, t) for t in tokens)


def _forbidden_hit(bag: set[str], tokens: list[str] | None) -> bool:
    if not tokens:
        return False
    return any(t in bag for t in tokens)


def _score_scenario(sc: dict[str, Any], bag: set[str]) -> Optional[dict[str, Any]]:
    """Return match detail or None if scenario does not qualify."""
    if _forbidden_hit(bag, sc.get("forbid")):
        return None
    required = sc.get("required") or []
    if required and not _has_all(bag, list(required)):
        return None
    req_any = sc.get("required_any") or []
    if req_any and not _has_any(bag, list(req_any)):
        return None

    from rca.ladder import token_satisfied

    supporting = [t for t in (sc.get("supporting_any") or []) if token_satisfied(bag, t)]
    req_hits = [t for t in list(required) if token_satisfied(bag, t)]
    req_any_hits = [t for t in list(req_any) if token_satisfied(bag, t)]
    hit_tokens = list(dict.fromkeys(req_hits + req_any_hits + supporting))
    coverage = _level_coverage_for_match(bag, hit_tokens)

    # Soft score: required satisfied + supporting hits + multi-layer agreement
    base = 1.0
    score = base + 0.08 * len(supporting) + 0.01 * float(sc.get("priority") or 0)
    # Excel taxonomy: independent L1/L2/L3 agreement strengthens the scenario
    agree = int(coverage.get("agree_count") or 0)
    if agree >= 3:
        score += 0.20
    elif agree == 2:
        score += 0.12
    elif agree == 1:
        score -= 0.04  # single-layer match is weaker (POSSIBLE territory)

    # Prefer matrix primary when ≥2 layers agree, or YAML opts in
    prefer = bool(sc.get("prefer_primary", False)) or agree >= 2

    return {
        "id": sc.get("id"),
        "title": sc.get("title"),
        "priority": int(sc.get("priority") or 0),
        "score": round(score, 4),
        "supporting": supporting,
        "hit_tokens": hit_tokens,
        "level_coverage": coverage,
        "compound_class": sc.get("compound_class"),
        "primary_hypothesis": sc.get("primary_hypothesis"),
        "fallback_hypothesis": sc.get("fallback_hypothesis"),
        "fallback_when_missing": list(sc.get("fallback_when_missing") or []),
        "traces": list(sc.get("traces") or []),
        "fallback_note": sc.get("fallback_note"),
        "prefer_primary": prefer,
        "asset": sc.get("asset"),
        "excel_row": sc.get("excel_row"),
        "levels": list(sc.get("levels") or ["L1", "L2", "L3"]),
    }


def evaluate_lbb_steps(bag: set[str], matrix: Optional[dict[str, Any]] = None) -> list[LbbStepResult]:
    m = matrix or load_matrix()
    out: list[LbbStepResult] = []
    for step in m.get("lbb_steps") or []:
        if not isinstance(step, dict):
            continue
        sid = int(step.get("id") or 0)
        label = str(step.get("label") or f"Step {sid}")
        note = step.get("note")
        forbid = list(step.get("forbid") or [])
        any_of = list(step.get("any_of") or [])
        # Step 10 style: PASS when forbidden token absent
        if step.get("require_absent_for_pass") and forbid:
            if _forbidden_hit(bag, forbid):
                out.append(
                    LbbStepResult(
                        id=sid,
                        label=label,
                        status="FAIL",
                        evidence=[t for t in forbid if t in bag],
                        note=note,
                    )
                )
            else:
                out.append(
                    LbbStepResult(
                        id=sid,
                        label=label,
                        status="PASS",
                        evidence=[],
                        note=note or "No bus-diff evidence — bus fault excluded",
                    )
                )
            continue
        if any_of:
            from rca.ladder import token_satisfied

            hits = [t for t in any_of if token_satisfied(bag, t)]
            out.append(
                LbbStepResult(
                    id=sid,
                    label=label,
                    status="PASS" if hits else "FAIL",
                    evidence=hits,
                    note=note,
                )
            )
        else:
            out.append(
                LbbStepResult(
                    id=sid, label=label, status="UNKNOWN", evidence=[], note=note
                )
            )
    return out


def apply_guardrails(
    bag: set[str], matrix: Optional[dict[str, Any]] = None
) -> list[dict[str, Any]]:
    m = matrix or load_matrix()
    actions: list[dict[str, Any]] = []
    for g in m.get("guardrails") or []:
        if not isinstance(g, dict):
            continue
        when_any = list(g.get("when_any") or [])
        unless = list(g.get("unless") or [])
        if when_any and not _has_any(bag, when_any):
            continue
        if unless and _has_any(bag, unless):
            continue
        actions.append(
            {
                "id": g.get("id"),
                "demote_hypothesis": g.get("demote_hypothesis"),
                "demote_to": g.get("demote_to") or "UNLIKELY",
                "reason": g.get("reason") or g.get("description"),
            }
        )
    return actions


def match_matrix(evidence_bag: set[str] | list[str]) -> MatrixMatchResult:
    """Pick highest-priority qualifying scenario and build compound / LBB payload."""
    bag = {str(t) for t in evidence_bag if t}
    m = load_matrix()
    version = str(m.get("version") or "unknown")
    candidates: list[dict[str, Any]] = []
    for sc in m.get("scenarios") or []:
        if not isinstance(sc, dict):
            continue
        detail = _score_scenario(sc, bag)
        if detail:
            candidates.append(detail)
    candidates.sort(key=lambda c: (c.get("priority", 0), c.get("score", 0)), reverse=True)

    result = MatrixMatchResult(matrix_version=version, candidates=candidates[:8])
    steps = evaluate_lbb_steps(bag, m)
    # Only attach full LBB checklist when cascade / BF context is present
    cascade_ctx = bool(
        "cascade_lbb_detected" in bag
        or "bf_logic_satisfied" in bag
        or ("intertrip_send_observed" in bag and "intertrip_receive_observed" in bag)
    )
    if cascade_ctx:
        result.lbb_steps = steps
        result.lbb_steps_total = len(steps)
        result.lbb_steps_passed = sum(1 for s in steps if s.status == "PASS")

    result.guardrail_actions = apply_guardrails(bag, m)

    if not candidates:
        return result

    top = candidates[0]
    primary = top.get("primary_hypothesis")
    missing_for_fb = list(top.get("fallback_when_missing") or [])
    if (
        top.get("fallback_hypothesis")
        and missing_for_fb
        and not _has_all(bag, missing_for_fb)
    ):
        primary = top.get("fallback_hypothesis")
        result.traces.append(
            f"Fallback to {primary} — missing {', '.join(missing_for_fb)}"
        )

    result.matched_scenario_id = top.get("id")
    result.matched_title = top.get("title")
    result.compound_class = top.get("compound_class")
    result.primary_hypothesis = primary
    result.fallback_hypothesis = top.get("fallback_hypothesis")
    result.level_coverage = dict(top.get("level_coverage") or {})
    result.prefer_primary = bool(top.get("prefer_primary"))
    result.traces.extend(list(top.get("traces") or []))
    ladder = (result.level_coverage or {}).get("ladder")
    agree = (result.level_coverage or {}).get("agree_count")
    if ladder:
        result.traces.append(
            f"Evidence ladder {ladder} (L1 digitals / L2 SOE-sequence / L3 DR) — "
            f"{agree or 0} layer(s) agree"
        )
    if top.get("fallback_note"):
        result.traces.append(str(top["fallback_note"]))
    if cascade_ctx and result.lbb_steps_total:
        result.traces.append(
            f"LBB checklist {result.lbb_steps_passed}/{result.lbb_steps_total} steps PASS"
        )
    return result


def apply_matrix_to_hypotheses(
    hypotheses: list[Any],
    matrix_result: MatrixMatchResult,
) -> None:
    """Demote hypotheses per matrix guardrails (in-place)."""
    demotions = {
        str(a.get("demote_hypothesis")): a
        for a in matrix_result.guardrail_actions
        if a.get("demote_hypothesis")
    }
    if not demotions:
        return
    for h in hypotheses:
        hid = getattr(h, "hypothesis_id", None) or (
            h.get("hypothesis_id") if isinstance(h, dict) else None
        )
        if hid not in demotions:
            continue
        action = demotions[str(hid)]
        target = str(action.get("demote_to") or "UNLIKELY")
        reason = str(action.get("reason") or "matrix guardrail")
        if isinstance(h, dict):
            h["status"] = target
            h["score"] = min(float(h.get("score") or 0), 0.15)
            contra = list(h.get("contradicting_evidence") or [])
            if "matrix_bus_guardrail" not in contra:
                contra.append("matrix_bus_guardrail")
            h["contradicting_evidence"] = contra
            expl = str(h.get("explanation") or "")
            h["explanation"] = (expl + " " + reason).strip()
        else:
            h.status = target
            h.score = min(float(h.score or 0), 0.15)
            contra = list(h.contradicting_evidence or [])
            if "matrix_bus_guardrail" not in contra:
                contra.append("matrix_bus_guardrail")
            h.contradicting_evidence = contra
            h.explanation = (str(h.explanation or "") + " " + reason).strip()
