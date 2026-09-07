"""Analysis orchestration — Celery enqueue or sync pipeline for MVP/dev."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import JobStage
from app.models import (
    AnalysisJob,
    ComtradeFile,
    ConsistencyFinding,
    Event,
    EventTimeline,
    Evidence,
    FaultClassification,
    Measurement,
    ProtectionOperation,
    RcaHypothesis,
)
from app.services.audit_service import write_audit
from app.services import event_service

logger = logging.getLogger(__name__)

PIPELINE_STAGES = [
    JobStage.FILE_DETECTION,
    JobStage.COMTRADE_VALIDATION,
    JobStage.PARSING,
    JobStage.SIGNAL_PROCESSING,
    JobStage.EVENT_RECONSTRUCTION,
    JobStage.PROTECTION_ANALYSIS,
    JobStage.CONSISTENCY_CHECKER,
    JobStage.FAULT_CLASSIFICATION,
    JobStage.RCA,
    JobStage.EVIDENCE,
    JobStage.REPORT,
    JobStage.COMPLETE,
]


def _component_versions() -> dict[str, str]:
    s = get_settings()
    return {
        "comtrade_parser": s.comtrade_parser_version,
        "signal_algorithm": s.signal_algorithm_version,
        "protection_rules": s.protection_rules_version,
        "consistency_rules": s.consistency_rules_version,
        "rca_engine": s.rca_engine_version,
        "report_template": s.report_template_version,
    }


async def enqueue_analysis(
    db: AsyncSession,
    event: Event,
    *,
    requested_by: Optional[str] = None,
    parameters: Optional[dict[str, Any]] = None,
    force: bool = False,
    request_id: Optional[str] = None,
    defer: bool = False,
) -> AnalysisJob:
    settings = get_settings()

    if not force:
        existing = await db.execute(
            select(AnalysisJob).where(
                AnalysisJob.event_id == event.id,
                AnalysisJob.status.in_(("PENDING", "RUNNING")),
            )
        )
        job = existing.scalar_one_or_none()
        if job is not None:
            return job

    job = AnalysisJob(
        event_id=event.id,
        requested_by=requested_by,
        status="PENDING",
        stage=JobStage.UPLOAD.value,
        progress=0.0,
        stages=[{"name": s.value, "status": "PENDING"} for s in PIPELINE_STAGES],
        current_message="Queued",
        component_versions=_component_versions(),
        parameters=parameters or {},
    )
    db.add(job)
    event.status = "ANALYZING"
    await db.flush()

    celery_task_id = None
    run_sync = (not defer) and (
        settings.run_analysis_sync or settings.app_env == "development"
    )

    if not run_sync and not defer:
        try:
            from workers.tasks import run_analysis_pipeline

            async_result = run_analysis_pipeline.delay(job.id)
            celery_task_id = async_result.id
            job.celery_task_id = celery_task_id
            job.current_message = "Queued on Celery"
            await db.flush()
        except Exception as exc:  # noqa: BLE001
            logger.warning("Celery unavailable (%s); running sync", exc)
            run_sync = True

    if defer:
        job.current_message = "Queued (background)"
        await db.flush()
    elif run_sync:
        await run_pipeline_stages(db, job, event)

    await write_audit(
        db,
        action="ANALYSE",
        user_id=requested_by,
        object_type="AnalysisJob",
        object_id=job.id,
        new_value={"event_id": event.id, "celery_task_id": celery_task_id, "defer": defer},
        request_id=request_id,
    )
    return job


async def run_job_by_id(job_id: str) -> None:
    """Background runner — own DB session so the HTTP request can return immediately."""
    from app.database import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        try:
            job = await get_job(db, job_id)
            if job is None:
                logger.error("Background analysis: job %s not found", job_id)
                return
            event = await event_service.get_event(db, job.event_id)
            if event is None:
                logger.error("Background analysis: event missing for job %s", job_id)
                return
            await run_pipeline_stages(db, job, event)
            await db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Background analysis failed for job %s", job_id)
            await db.rollback()
            try:
                async with AsyncSessionLocal() as db2:
                    job = await get_job(db2, job_id)
                    if job is not None:
                        job.status = "FAILED"
                        job.stage = JobStage.FAILED.value
                        job.error_message = "Background analysis failed — see server logs"
                        job.finished_at = datetime.now(timezone.utc)
                        event = await event_service.get_event(db2, job.event_id)
                        if event is not None:
                            event.status = "FAILED"
                        await db2.commit()
            except Exception:  # noqa: BLE001
                logger.exception("Could not mark job %s failed", job_id)


async def run_pipeline_stages(
    db: AsyncSession,
    job: AnalysisJob,
    event: Event,
) -> None:
    """
    MVP deterministic pipeline: advance stages and seed placeholder engineering
    artefacts so API consumers can exercise the full read path.
    Real signal/RCA engines plug in here when available.
    """
    job.status = "RUNNING"
    job.started_at = datetime.now(timezone.utc)
    stages_state = list(job.stages or [])
    n = len(PIPELINE_STAGES)

    try:
        for i, stage in enumerate(PIPELINE_STAGES):
            job.stage = stage.value
            job.progress = round(((i + 1) / n) * 100.0, 2)
            job.current_message = f"Running {stage.value}"
            if i < len(stages_state):
                stages_state[i] = {
                    "name": stage.value,
                    "status": "RUNNING",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                }
            job.stages = stages_state
            await db.flush()

            await _execute_stage(db, event, stage)

            if i < len(stages_state):
                stages_state[i]["status"] = "COMPLETED"
                stages_state[i]["finished_at"] = datetime.now(timezone.utc).isoformat()
            job.stages = stages_state
            await db.flush()

        job.status = "COMPLETED"
        job.stage = JobStage.COMPLETE.value
        job.progress = 100.0
        job.current_message = "Analysis complete"
        job.finished_at = datetime.now(timezone.utc)
        job.result_summary = {
            "decision_state": event.decision_state or "ENGINEER_REVIEW_REQUIRED",
            "data_quality": event.data_quality or "ACCEPTABLE",
        }
        event.status = "REVIEW"
        event.decision_state = event.decision_state or "ENGINEER_REVIEW_REQUIRED"
        event.data_quality = event.data_quality or "ACCEPTABLE"
        await db.flush()
    except Exception as exc:  # noqa: BLE001
        logger.exception("Analysis failed for job %s", job.id)
        job.status = "FAILED"
        job.stage = JobStage.FAILED.value
        job.error_message = str(exc)
        job.finished_at = datetime.now(timezone.utc)
        event.status = "FAILED"
        await db.flush()
        raise


async def _execute_stage(db: AsyncSession, event: Event, stage: JobStage) -> None:
    """Stage hooks — prefer real COMTRADE/protection engines; fall back carefully."""
    settings = get_settings()

    if stage in (
        JobStage.FILE_DETECTION,
        JobStage.COMTRADE_VALIDATION,
        JobStage.PARSING,
    ):
        from app.services.waveform_service import ingest_and_persist_comtrade

        result = await ingest_and_persist_comtrade(db, event)
        if not result.get("success") and stage == JobStage.PARSING:
            event.decision_state = event.decision_state or "UNSUPPORTED_FORMAT"
            event.data_quality = event.data_quality or "INVALID"
        elif result.get("success") and stage == JobStage.PARSING:
            # Clear sticky failure from a prior bad parse so Overview/tabs refresh
            if (event.decision_state or "").upper() == "UNSUPPORTED_FORMAT":
                event.decision_state = "ENGINEER_REVIEW_REQUIRED"
            if (event.data_quality or "").upper() in ("INVALID", "POOR"):
                event.data_quality = "ACCEPTABLE"
        return

    if stage == JobStage.SIGNAL_PROCESSING:
        # Skip engineering when COMTRADE never persisted (hard parse failure)
        ct_row = (
            await db.execute(
                select(ComtradeFile).where(ComtradeFile.event_id == event.id).limit(1)
            )
        ).scalar_one_or_none()
        if ct_row is None:
            logger.warning(
                "Skipping engineering for event %s — no COMTRADE metadata persisted",
                event.id,
            )
            return

        # Run full engineering pipeline once (fault, protection, timeline, RCA…)
        from app.services.engineering_persist import persist_engineering_analysis

        try:
            eng = await persist_engineering_analysis(db, event, force=True)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Engineering pipeline crashed")
            eng = {"success": False, "error": str(exc)}
        if not eng.get("success"):
            logger.warning("Engineering pipeline: %s", eng.get("error"))
            existing = await db.execute(
                select(Measurement).where(Measurement.event_id == event.id).limit(1)
            )
            if existing.scalar_one_or_none() is None:
                db.add(
                    Measurement(
                        event_id=event.id,
                        quantity="Ia_rms",
                        phase="A",
                        value=None,
                        unit="A",
                        algorithm="pending_full_electrical",
                        algorithm_version=settings.signal_algorithm_version,
                        quality="NOT_VALIDATED",
                    )
                )
        return

    if stage == JobStage.EVENT_RECONSTRUCTION:
        existing = await db.execute(
            select(EventTimeline).where(EventTimeline.event_id == event.id).limit(1)
        )
        if existing.scalar_one_or_none() is None:
            db.add(
                EventTimeline(
                    event_id=event.id,
                    sequence=1,
                    t_us=0,
                    event_type="RECORD_START",
                    source="PIPELINE",
                    label="Disturbance record start",
                    confidence=1.0,
                )
            )
        return

    if stage == JobStage.PROTECTION_ANALYSIS:
        existing = await db.execute(
            select(ProtectionOperation)
            .where(ProtectionOperation.event_id == event.id)
            .limit(1)
        )
        if existing.scalar_one_or_none() is None:
            # Leave empty rather than inventing trips — consistency/RCA handle UNKNOWN
            pass
        return

    if stage == JobStage.CONSISTENCY_CHECKER:
        from consistency import ConsistencyEngine
        from protection.models import ElementContext, ElementObservation
        from protection.elements.el_51 import ELEMENT as EL51

        existing = await db.execute(
            select(ConsistencyFinding)
            .where(ConsistencyFinding.event_id == event.id)
            .limit(1)
        )
        if existing.scalar_one_or_none() is None:
            # If no observations, record UNVERIFIABLE explicitly
            obs = ElementObservation(element="51")
            ctx = ElementContext(
                observations=obs,
                settings={},
                setting_resolutions={},
                electrical={},
                rule_config={},
            )
            assessment = EL51.assess(ctx)
            cons = ConsistencyEngine().run(
                event_id=event.event_id, assessments=[assessment], timeline=[]
            )
            for f in cons.findings:
                conf = f.confidence
                try:
                    conf_f = float(conf) if conf not in (None, "INCONCLUSIVE", "LOW", "MEDIUM", "HIGH") else None
                except (TypeError, ValueError):
                    conf_f = None
                db.add(
                    ConsistencyFinding(
                        event_id=event.id,
                        element=f.element,
                        check_type=f.check_type,
                        setting_source=f.setting_source,
                        setting_version=f.setting_version,
                        expected={"value": f.expected} if not isinstance(f.expected, dict) else f.expected,
                        observed={"value": f.observed} if not isinstance(f.observed, dict) else f.observed,
                        status=f.status,
                        severity=f.severity,
                        explanation=f.explanation,
                        confidence=conf_f,
                        evidence_ids=f.evidence_ids,
                        rule_version=settings.consistency_rules_version,
                    )
                )
            if cons.rca_must_remain_inconclusive:
                event.decision_state = "INCONCLUSIVE"
        return

    if stage == JobStage.FAULT_CLASSIFICATION:
        existing = await db.execute(
            select(FaultClassification)
            .where(FaultClassification.event_id == event.id)
            .limit(1)
        )
        if existing.scalar_one_or_none() is None:
            has_ct = (
                await db.execute(
                    select(ComtradeFile).where(ComtradeFile.event_id == event.id).limit(1)
                )
            ).scalar_one_or_none()
            # Do not seed a fake UNKNOWN when parse never produced COMTRADE
            if has_ct is None:
                return
            db.add(
                FaultClassification(
                    event_id=event.id,
                    fault_type="UNKNOWN",
                    status="INCONCLUSIVE",
                    confidence=0.0,
                    confidence_level="INCONCLUSIVE",
                    explanation="Insufficient validated electrical evidence for fault type",
                    distance_km=None,
                    is_primary=True,
                )
            )
        return

    if stage == JobStage.RCA:
        existing = await db.execute(
            select(RcaHypothesis).where(RcaHypothesis.event_id == event.id).limit(1)
        )
        if existing.scalar_one_or_none() is None:
            from consistency.engine import ConsistencyResult
            from fault_analysis import FaultClassificationResult
            from rca import HypothesisEngine

            findings = (
                await db.execute(
                    select(ConsistencyFinding).where(ConsistencyFinding.event_id == event.id)
                )
            ).scalars().all()
            critical = any(
                f.status == "INCONSISTENT" and (f.severity or "").upper() in ("HIGH", "CRITICAL")
                for f in findings
            )
            cons = ConsistencyResult(
                findings=[],
                has_critical_setting_inconsistency=critical,
                rca_must_remain_inconclusive=critical
                or (event.decision_state or "") == "INCONCLUSIVE",
                summary_status="INCONSISTENT" if critical else "UNVERIFIABLE",
            )
            rca = HypothesisEngine().run(
                fault=FaultClassificationResult(
                    fault_type="UNKNOWN", status="UNKNOWN", confidence="LOW"
                ),
                assessments=[],
                consistency=cons,
                electrical_flags={},
            )
            for i, h in enumerate(rca.hypotheses[:8], start=1):
                db.add(
                    RcaHypothesis(
                        event_id=event.id,
                        hypothesis_code=h.hypothesis_id,
                        title=(
                            getattr(h, "title", None)
                            or h.hypothesis_id.replace("_", " ").title()
                        ),
                        statement=h.statement
                        or f"Status={h.status}; score={h.score:.3f}",
                        status=h.status,
                        rank=i,
                        confidence=h.score,
                        confidence_level=h.confidence,
                        supporting_evidence_ids=h.supporting_evidence,
                        contradicting_evidence_ids=h.contradicting_evidence,
                        engine_version=settings.rca_engine_version,
                        recommended_actions=list(h.recommended_actions)
                        or [
                            "Verify active setting group",
                            "Review consistency findings",
                        ],
                        explanation=h.explanation or None,
                        extra={"missing_evidence": h.missing_evidence},
                    )
                )
            if rca.forced_inconclusive:
                event.decision_state = "INCONCLUSIVE"
        return

    if stage == JobStage.EVIDENCE:
        existing = await db.execute(
            select(Evidence).where(Evidence.event_id == event.id).limit(1)
        )
        if existing.scalar_one_or_none() is None:
            db.add(
                Evidence(
                    event_id=event.id,
                    source_type="CALCULATION",
                    polarity="NEUTRAL",
                    title="Analysis pipeline executed",
                    summary="Deterministic pipeline completed without generative AI.",
                    confidence=1.0,
                )
            )
        # Store similarity links (classical features)
        from app.services.similarity_service import index_and_link_similar

        await index_and_link_similar(db, event)
        return

    if stage == JobStage.REPORT:
        from app.services import report_service

        await db.refresh(event)
        await report_service.generate_report(
            db, event, report_type="RCA", fmt="HTML", generated_by=None
        )
        return

    await db.flush()


async def get_job(db: AsyncSession, job_id: str) -> Optional[AnalysisJob]:
    result = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
    return result.scalar_one_or_none()


async def latest_job_for_event(
    db: AsyncSession, event_id: str
) -> Optional[AnalysisJob]:
    result = await db.execute(
        select(AnalysisJob)
        .where(AnalysisJob.event_id == event_id)
        .order_by(AnalysisJob.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
