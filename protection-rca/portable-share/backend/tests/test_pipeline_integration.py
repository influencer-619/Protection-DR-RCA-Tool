"""End-to-end pipeline: parse COMTRADE → analyze → consistency → RCA → report."""

from __future__ import annotations

from pathlib import Path

from app.services.analysis_pipeline import AnalysisPipeline
from comtrade import ComtradeService
from comtrade.detector.service import ComtradeDetectionService
from settings.hierarchy.resolver import SettingRecord, SettingSource


FIXTURE_DIR = (
    Path(__file__).resolve().parents[2] / "test_data" / "comtrade" / "ieee_1999"
)


def test_full_pipeline_ag_fault_fixture():
    cfg = FIXTURE_DIR / "ag_fault.cfg"
    dat = FIXTURE_DIR / "ag_fault.dat"
    assert cfg.exists() and dat.exists()

    ingest = ComtradeService().ingest([cfg, dat])
    assert ingest.record is not None
    assert ingest.validation is not None
    status = ingest.validation.status
    status_s = status.value if hasattr(status, "value") else str(status)
    assert status_s in {
        "VALID",
        "VALID_WITH_WARNINGS",
        "PARTIALLY_SUPPORTED",
    }

    settings = [
        SettingRecord(
            setting_id="s-51-en",
            relay_id="relay-1",
            setting_group="Base",
            parameter="51_ENABLED",
            value=False,
            unit="",
            enabled=False,
            version="RS-TEST-001",
            source=SettingSource.APPROVED_RELAY_BASE,
            approval_status="APPROVED",
            verified=False,
            element="51",
        )
    ]

    result = AnalysisPipeline().run(
        ingest.record,
        event_meta={
            "event_id": "EVT-SYNTH-AG-001",
            "description": "Synthetic AG fault regression",
        },
        setting_candidates=settings,
    )

    assert result.fault_classification
    assert result.decision
    assert result.report
    decision_state = result.decision.get("state") or result.decision.get("status")
    assert decision_state in {
        "INCONCLUSIVE",
        "ANALYSIS_COMPLETE_WITH_WARNINGS",
        "ENGINEER_REVIEW_REQUIRED",
        "ANALYSIS_COMPLETE",
        "DATA_INSUFFICIENT",
    }
    rca = result.rca_hypotheses or {}
    hyps = rca.get("hypotheses") or rca.get("ranked") or []
    if isinstance(hyps, list):
        for h in hyps:
            if isinstance(h, dict) and h.get("status") == "CONFIRMED":
                assert h.get("supporting_evidence"), "CONFIRMED requires evidence"


def test_comtrade_detect_api_shape():
    cfg = FIXTURE_DIR / "ag_fault.cfg"
    dat = FIXTURE_DIR / "ag_fault.dat"
    det = ComtradeDetectionService().detect([cfg, dat])
    assert det.standard
    assert det.revision
    assert det.container
    assert 0.0 <= float(det.confidence) <= 1.0
    assert det.status in {
        "SUPPORTED",
        "PARTIALLY_SUPPORTED",
        "UNSUPPORTED",
        "NOT_VALIDATED",
    }


def test_ieee_2013_fixture_parses():
    d = Path(__file__).resolve().parents[2] / "test_data" / "comtrade" / "ieee_2013"
    cfg, dat = d / "mixed_event.cfg", d / "mixed_event.dat"
    assert cfg.exists() and dat.exists()
    ingest = ComtradeService().ingest([cfg, dat])
    assert ingest.success, ingest.error
    assert ingest.record is not None
    assert ingest.record.samples > 0
