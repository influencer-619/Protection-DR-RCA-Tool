"""Cause enrichment + scheme library unit tests."""

from __future__ import annotations

from consistency.engine import ConsistencyResult
from fault_analysis import FaultClassificationResult
from protection.models import ProtectionAssessment
from protection.schemes import detect_schemes, load_scheme_profiles, scheme_tokens
from rca import HypothesisEngine
from rca.enrichment import (
    collect_enrichment_tokens,
    tokens_from_asset,
    tokens_from_cause_evidence,
)


def _line_21_fault():
    fault = FaultClassificationResult(
        fault_type="AG",
        status="CLASSIFIED",
        confidence="HIGH",
        evidence={"available": True, "Ia_elevated": True, "ground": True},
    )
    assessments = [
        ProtectionAssessment(
            element="21",
            enabled=True,
            pickup=True,
            trip=True,
            expected_operation="OPERATE",
            actual_operation="OPERATED",
            timing=None,
            consistency="CONSISTENT",
            setting_reference={},
            evidence_ids=["e"],
            confidence="MEDIUM",
        )
    ]
    return fault, assessments


def test_scheme_library_loads_profiles():
    profiles = load_scheme_profiles()
    ids = {p.id for p in profiles}
    assert "line_distance_stepped" in ids
    assert "xfmr_unit" in ids
    assert "pilot_pott" in ids


def test_detect_line_distance_scheme():
    matches = detect_schemes(operated_elements=["21"], enabled_elements=["21", "51"])
    assert matches
    assert matches[0].scheme_id == "line_distance_stepped"
    assert matches[0].distance_applicable is True
    toks = scheme_tokens(matches)
    assert "scheme_library_matched" in toks
    assert "scheme_id_line_distance_stepped" in toks


def test_detect_xfmr_unit_scheme():
    matches = detect_schemes(operated_elements=["87T"], enabled_elements=["87T"])
    assert matches[0].scheme_id == "xfmr_unit"
    assert matches[0].distance_applicable is False


def test_cable_asset_token():
    assert "cable_asset_confirmed" in tokens_from_asset("CABLE")
    assert not tokens_from_asset("LINE")


def test_engineer_lightning_promotes_cause():
    fault, assessments = _line_21_fault()
    toks, _, detail = collect_enrichment_tokens(
        cause_evidence=["lightning_evidence"],
    )
    assert "lightning_evidence" in toks
    assert detail["tokens"]

    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={"current_increase": True},
        extra_evidence=toks,
    )
    by_id = {h.hypothesis_id: h for h in rca.hypotheses}
    assert by_id["LIGHTNING"].status in ("POSSIBLE", "PROBABLE", "CONFIRMED")
    assert by_id["LIGHTNING"].status != "INCONCLUSIVE"
    # Zone primary remains line
    assert rca.primary is not None
    assert rca.primary.hypothesis_id == "EXTERNAL_LINE_FAULT"


def test_without_enrichment_lightning_stays_inconclusive():
    fault, assessments = _line_21_fault()
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=assessments,
        consistency=ConsistencyResult(summary_status="CONSISTENT"),
        electrical_flags={"current_increase": True},
    )
    by_id = {h.hypothesis_id: h for h in rca.hypotheses}
    assert by_id["LIGHTNING"].status == "INCONCLUSIVE"


def test_cause_evidence_aliases():
    assert "field_report_vegetation" in tokens_from_cause_evidence(["vegetation"])
    assert "cable_asset_confirmed" in tokens_from_cause_evidence({"cable": True})
