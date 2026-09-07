"""Celery tasks — analysis pipeline stages updating AnalysisJob progress."""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from workers.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run async coroutine from sync Celery worker."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


async def _pipeline(job_id: str) -> dict:
    from app.database import AsyncSessionLocal
    from app.models import AnalysisJob, Event
    from app.services.analysis_service import run_pipeline_stages

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(select(AnalysisJob).where(AnalysisJob.id == job_id))
            job = result.scalar_one_or_none()
            if job is None:
                return {"ok": False, "error": "job not found"}
            event = await db.get(Event, job.event_id)
            if event is None:
                job.status = "FAILED"
                job.error_message = "Event not found"
                await db.commit()
                return {"ok": False, "error": "event not found"}
            await run_pipeline_stages(db, job, event)
            await db.commit()
            return {"ok": True, "job_id": job_id, "status": job.status}
        except Exception as exc:  # noqa: BLE001
            await db.rollback()
            logger.exception("Pipeline task failed for %s", job_id)
            # Best-effort mark failed
            async with AsyncSessionLocal() as db2:
                job2 = await db2.get(AnalysisJob, job_id)
                if job2 is not None:
                    job2.status = "FAILED"
                    job2.error_message = str(exc)
                    await db2.commit()
            return {"ok": False, "error": str(exc)}


@celery_app.task(name="workers.tasks.run_analysis_pipeline", bind=True, max_retries=1)
def run_analysis_pipeline(self, job_id: str) -> dict:
    """
    Execute analysis pipeline for an AnalysisJob.

    Stages update job.progress / job.stage. No OT control actions are performed.
    """
    logger.info("Starting analysis pipeline job_id=%s task_id=%s", job_id, self.request.id)
    return _run_async(_pipeline(job_id))
