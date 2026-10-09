"""Stage C — executable matrix_v1 + compound LBB + bus guardrail."""

from __future__ import annotations

from consistency.engine import ConsistencyResult
from fault_analysis import FaultClassificationResult
from protection.models import ProtectionAssessment
from rca import HypothesisEngine
from rca.matrix import evaluate_lbb_steps, load_matrix, match_matrix, reload_matrix


def test_matrix_loads_versioned_pack():
    reload_matrix()
    m = load_matrix()
    assert m.get("version") in ("1.0.0", "1.1.0")
    assert len(m.get("scenarios") or []) >= 7
    ids = {s.get("id") for s in m.get("scenarios") or []}
    assert "SC_LBB_CASCADE_COMPOUND" in ids
    assert "SC_FEEDER_INZONE" in ids
    assert "SC_XFMR_INTERNAL_THROUGH_EXCLUDED" in ids
    assert "SC_INRUSH_ENERGIZATION_FALLBACK" in ids
    assert len(m.get("lbb_steps") or []) == 10


def test_matrix_lbb_cascade_compound():
    bag = {
        "cascade_lbb_detected",
        "bf_logic_satisfied",
        "current_persists",
        "intertrip_send_observed",
        "intertrip_receive_observed",
        "fault_classified",
        "trip_command_observed",
        "protection_operated",
    }
    r = match_matrix(bag)
    assert r.matched_scenario_id == "SC_LBB_CASCADE_COMPOUND"
    assert r.compound_class == "FAULT + LOCAL BREAKER FAILURE + LBB/CASCADE CLEARING"
    assert r.primary_hypothesis == "BREAKER_FAILURE"
    assert r.lbb_steps_total == 10
    assert r.lbb_steps_passed >= 7
    assert any("bus" in t.lower() or "87B" in t or "SC_LBB" in t for t in r.traces)


def test_matrix_feeder_inzone():
    bag = {
        "fault_classified",
        "protection_operated",
        "earth_fault_element_operated",
        "current_increase_observed",
        "scheme_earth_fault",
    }
    r = match_matrix(bag)
    assert r.matched_scenario_id == "SC_FEEDER_INZONE"
    assert "IN-ZONE" in (r.compound_class or "").upper()
    assert "EARTH" in (r.compound_class or "").upper() or "FEEDER" in (
        r.compound_class or ""
    ).upper()


def test_matrix_xfmr_through_excluded():
    bag = {
        "differential_operated",
        "through_fault_excluded",
        "transformer_diff_operated",
        "fault_classified",
    }
    r = match_matrix(bag)
    assert r.matched_scenario_id == "SC_XFMR_INTERNAL_THROUGH_EXCLUDED"


def test_matrix_inrush_fallback():
    bag = {
        "magnetizing_inrush_possible",
        "switching_event_correlated",
        "harmonic_evidence",
        "electrical_no_fault",
    }
    r = match_matrix(bag)
    assert r.matched_scenario_id == "SC_INRUSH_ENERGIZATION_FALLBACK"
    cc = (r.compound_class or "").upper()
    assert "INRUSH" in cc or "ENERGIZATION" in cc


def test_lbb_step10_bus_excluded_without_87b():
    bag = {"cascade_lbb_detected", "bf_logic_satisfied", "fault_classified"}
    steps = evaluate_lbb_steps(bag)
    step10 = next(s for s in steps if s.id == 10)
    assert step10.status == "PASS"


def test_lbb_step10_fails_when_bus_diff_present():
    bag = {"cascade_lbb_detected", "bus_diff_operated"}
    steps = evaluate_lbb_steps(bag)
    step10 = next(s for s in steps if s.id == 10)
    assert step10.status == "FAIL"


def test_engine_bus_guardrail_on_cascade():
    fault = FaultClassificationResult(
        fault_type="AG", status="CLASSIFIED", confidence="MEDIUM", evidence={"ground": True}
    )
    assessments = [
        ProtectionAssessment(
            element="50BF",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["bf"],
            confidence="MEDIUM",
        )
    ]
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={
            "current_increase": True,
            "cascade_lbb_detected": True,
            "current_persists": True,
            "trip_command": True,
            "intertrip_send_seen": True,
            "intertrip_receive_seen": True,
        },
        extra_evidence={
            "cascade_lbb_detected",
            "bf_logic_satisfied",
            "current_persists",
            "intertrip_send_observed",
            "intertrip_receive_observed",
            "trip_command_observed",
        },
    )
    assert rca.matrix.get("matched_scenario_id") == "SC_LBB_CASCADE_COMPOUND"
    assert rca.matrix.get("compound_class")
    bus = next(h for h in rca.hypotheses if h.hypothesis_id == "BUS_ZONE_FAULT")
    assert bus.status == "UNLIKELY"
    assert "matrix_bus_guardrail" in (bus.contradicting_evidence or [])
