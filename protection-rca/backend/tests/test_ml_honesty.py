"""ML-014 — unavailable ML/similarity must not invent confidence."""

from __future__ import annotations

from consistency.engine import ConsistencyResult
from fault_analysis import FaultClassificationResult
from rca import HypothesisEngine


def test_supporting_scores_mark_ml_and_similarity_unavailable():
    fault = FaultClassificationResult(
        fault_type="AG", status="CLASSIFIED", confidence="MEDIUM"
    )
    cons = ConsistencyResult(summary_status="OK")
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=[],
        consistency=cons,
        electrical_flags={"fault_indicated": True, "current_increase": True},
        ml_available=False,
        similarity_available=False,
    )
    scores = rca.supporting_scores
    assert scores["ml"]["available"] is False
    assert scores["ml"]["status"] == "NOT_AVAILABLE"
    assert scores["similarity"]["available"] is False
    assert scores["similarity"]["status"] == "NOT_AVAILABLE"
    # Honesty via supporting_scores — not report/limitation banners
    assert not any("ml" in str(lim).lower() for lim in rca.limitations)
    assert not any("similarity" in str(lim).lower() for lim in rca.limitations)
    d = rca.to_dict()
    assert d["supporting_scores"]["ml"]["status"] == "NOT_AVAILABLE"
    assert "zero" in (scores["ml"]["message"] or "").lower()


def test_rca_still_ranks_when_ml_weight_effectively_zero():
    """Acceptance: RCA works with ml unavailable (weight contribution = 0)."""
    fault = FaultClassificationResult(
        fault_type="ABC", status="CLASSIFIED", confidence="HIGH"
    )
    cons = ConsistencyResult(summary_status="OK")
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=[],
        consistency=cons,
        electrical_flags={"fault_indicated": True, "current_increase": True},
        ml_available=False,
        ml_supports={"EXTERNAL_LINE_FAULT": 1.0},  # ignored when unavailable
        similarity_available=False,
    )
    assert rca.primary is not None
    assert len(rca.hypotheses) >= 1
    # Deterministic path still produces a primary without ML
    assert rca.primary.hypothesis_id
    assert rca.primary.confidence is not None


def test_ml_available_flag_surfaces_ok_status():
    fault = FaultClassificationResult(
        fault_type="AG", status="CLASSIFIED", confidence="MEDIUM"
    )
    cons = ConsistencyResult(summary_status="OK")
    rca = HypothesisEngine().run(
        fault=fault,
        assessments=[],
        consistency=cons,
        electrical_flags={"fault_indicated": True},
        ml_available=True,
        similarity_available=True,
    )
    assert rca.supporting_scores["ml"]["available"] is True
    assert rca.supporting_scores["ml"]["status"] == "OK"
    assert rca.supporting_scores["similarity"]["status"] == "OK"
