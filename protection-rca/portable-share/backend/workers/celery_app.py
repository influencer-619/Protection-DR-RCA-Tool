"""Celery application for Protection RCA analysis workers."""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "protection_rca",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    # OT safety: never schedule control-related tasks
    task_routes={"workers.tasks.run_analysis_pipeline": {"queue": "analysis"}},
)

# Alias used by `celery -A workers.celery_app worker`
app = celery_app
