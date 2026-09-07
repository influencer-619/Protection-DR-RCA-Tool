"""Engineer review / approve API — analysis disposition only (no OT control)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import EngineerReview, User
from app.schemas.review import ReviewApprove, ReviewCreate, ReviewOut
from app.services import event_service
from app.services.audit_service import write_audit
from app.services.report_service import generate_report

router = APIRouter(prefix="/api/review", tags=["review"])


def _persist_review_on_event(event, review: EngineerReview) -> None:
    """Keep report snapshot in sync so regenerations / exports see the disposition."""
    from app.services.report_service import _format_engineer_review

    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    snap = dict(extra.get("report_analysis") or {})
    snap["engineer_review"] = _format_engineer_review(review)
    extra["report_analysis"] = snap
    extra["latest_engineer_review"] = {
        "action": review.action,
        "decision_state": review.decision_state,
        "comments": review.comments,
        "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
    }
    event.extra = extra
    flag_modified(event, "extra")


@router.post("", response_model=ReviewOut, status_code=status.HTTP_201_CREATED)
async def submit_review(
    body: ReviewCreate,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.PROTECTION_ENGINEER)),
) -> ReviewOut:
    event = await event_service.get_event(db, body.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    review = EngineerReview(
        event_id=event.id,
        reviewer_id=user.id,
        action=body.action,
        decision_state=body.decision_state,
        comments=body.comments,
        modifications=body.modifications,
        reviewed_at=datetime.now(timezone.utc),
    )
    if body.decision_state:
        event.decision_state = body.decision_state
    if body.action == "ACCEPT":
        event.status = "CLOSED"
    elif body.action == "REJECT":
        event.status = "REVIEW"
    db.add(review)
    await db.flush()
    _persist_review_on_event(event, review)
    await db.flush()
    await write_audit(
        db,
        action="REVIEW",
        user_id=user.id,
        object_type="EngineerReview",
        object_id=review.id,
        new_value={"action": body.action, "event_id": event.id},
        request_id=getattr(request.state, "request_id", None),
    )
    try:
        await generate_report(
            db, event, report_type="RCA", title=None, fmt="HTML", generated_by=user.id
        )
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception(
            "Report regenerate after review failed: %s", exc
        )
    return ReviewOut.model_validate(review)


@router.post("/approve", response_model=ReviewOut)
async def approve_review(
    body: ReviewApprove,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.APPROVER)),
) -> ReviewOut:
    event = await event_service.get_event(db, body.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    review = EngineerReview(
        event_id=event.id,
        reviewer_id=user.id,
        action="ACCEPT",
        decision_state=body.decision_state or "ANALYSIS_COMPLETE",
        comments=body.comments,
        reviewed_at=datetime.now(timezone.utc),
    )
    event.status = "CLOSED"
    event.decision_state = body.decision_state or "ANALYSIS_COMPLETE"
    db.add(review)
    await db.flush()
    _persist_review_on_event(event, review)
    await db.flush()
    await write_audit(
        db,
        action="APPROVE",
        user_id=user.id,
        object_type="Event",
        object_id=event.id,
        new_value={"status": event.status, "decision_state": event.decision_state},
        request_id=getattr(request.state, "request_id", None),
    )
    try:
        await generate_report(
            db, event, report_type="RCA", title=None, fmt="HTML", generated_by=user.id
        )
    except Exception as exc:  # noqa: BLE001
        import logging

        logging.getLogger(__name__).exception(
            "Report regenerate after approve failed: %s", exc
        )
    return ReviewOut.model_validate(review)


@router.get("/event/{event_id}", response_model=list[ReviewOut])
async def list_reviews(
    event_id: str, db: DbSession, user: CurrentUser
) -> list[ReviewOut]:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    rows = (
        await db.execute(
            select(EngineerReview)
            .where(EngineerReview.event_id == event.id)
            .order_by(EngineerReview.reviewed_at.desc())
        )
    ).scalars().all()
    return [ReviewOut.model_validate(r) for r in rows]
