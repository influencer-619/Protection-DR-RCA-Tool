"""Analysis job heal / orphan queue — Stage B REL-008."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.analysis_service import (
    event_has_prior_results,
    heal_stuck_analysis,
    job_age_seconds,
)


def _job(**kwargs):
    now = datetime.now(timezone.utc)
    defaults = dict(
        id="job-1",
        event_id="evt-1",
        status="PENDING",
        stage="UPLOAD",
        progress=0.0,
        started_at=None,
        finished_at=None,
        created_at=now - timedelta(seconds=30),
        parameters={},
        current_message="Queued",
        error_message=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _event(**kwargs):
    defaults = dict(
        id="evt-1",
        status="ANALYZING",
        decision_state=None,
        fault_type=None,
        extra={},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_job_age_seconds_positive():
    j = _job(created_at=datetime.now(timezone.utc) - timedelta(seconds=12))
    assert job_age_seconds(j) >= 11.0


def test_event_has_prior_results_cascade_shell():
    ev = _event(
        extra={"cascade": {"primary_hypothesis": "BREAKER_FAILURE"}},
    )
    assert event_has_prior_results(ev) is True


def test_event_has_prior_combined_ready_alone_not_done():
    ev = _event(extra={"combined_ready": True})
    assert event_has_prior_results(ev) is False


@pytest.mark.asyncio
async def test_heal_does_not_touch_running_job():
    job = _job(status="RUNNING", started_at=datetime.now(timezone.utc), progress=0.4)
    event = _event(status="ANALYZING")
    db = MagicMock()
    db.flush = AsyncMock()
    out = await heal_stuck_analysis(db, event, job, orphan_after_s=1.0)
    assert out.status == "RUNNING"
    assert event.status == "ANALYZING"


@pytest.mark.asyncio
async def test_heal_orphan_pending_rekicks_once():
    job = _job(status="PENDING", progress=0.0, parameters={})
    event = _event(status="ANALYZING")
    db = MagicMock()
    db.flush = AsyncMock()
    with patch(
        "app.services.analysis_service.schedule_deferred_job", return_value=True
    ) as sched:
        out = await heal_stuck_analysis(db, event, job, orphan_after_s=1.0)
    assert out.status == "PENDING"
    assert out.parameters.get("_orphan_rekick") is True
    sched.assert_called_once_with(job.id)


@pytest.mark.asyncio
async def test_heal_orphan_pending_waits_after_rekick():
    job = _job(
        status="PENDING",
        progress=0.0,
        parameters={
            "_orphan_rekick": True,
            "_orphan_rekick_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    event = _event(status="ANALYZING")
    db = MagicMock()
    db.flush = AsyncMock()
    out = await heal_stuck_analysis(db, event, job, orphan_after_s=25.0)
    assert out.status == "PENDING"


@pytest.mark.asyncio
async def test_heal_orphan_pending_fails_after_rekick_window():
    old = (datetime.now(timezone.utc) - timedelta(seconds=40)).isoformat()
    job = _job(
        status="PENDING",
        progress=0.0,
        parameters={"_orphan_rekick": True, "_orphan_rekick_at": old},
    )
    event = _event(status="ANALYZING", fault_type=None, decision_state=None, extra={})
    db = MagicMock()
    db.flush = AsyncMock()
    out = await heal_stuck_analysis(db, event, job, orphan_after_s=1.0)
    assert out.status == "FAILED"
    assert "Orphaned queue" in (out.error_message or "")
    assert event.status == "FAILED"


@pytest.mark.asyncio
async def test_heal_sticky_analyzing_to_review_when_prior_exists():
    job = _job(status="COMPLETED", progress=1.0)
    event = _event(
        status="ANALYZING",
        decision_state="ANALYSIS_COMPLETE",
    )
    db = MagicMock()
    db.flush = AsyncMock()
    await heal_stuck_analysis(db, event, job, orphan_after_s=1.0)
    assert event.status == "REVIEW"
