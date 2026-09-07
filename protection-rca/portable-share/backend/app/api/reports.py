"""Reports API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import Response

from app.core.security import Role
from app.models import User
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.schemas.reports import ReportCreate, ReportListResponse, ReportOut
from app.services import event_service, report_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.post("", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
async def create_report(
    body: ReportCreate,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> ReportOut:
    event = await event_service.get_event(db, body.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    report = await report_service.generate_report(
        db,
        event,
        report_type=body.report_type,
        title=body.title,
        fmt=body.format,
        generated_by=user.id,
        request_id=getattr(request.state, "request_id", None),
    )
    return ReportOut.model_validate(report)


@router.get("/by-event/{event_id}", response_model=ReportListResponse)
async def list_reports_for_event(
    event_id: str, db: DbSession, user: CurrentUser
) -> ReportListResponse:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    items = await report_service.list_reports(db, event.id)
    return ReportListResponse(
        items=[ReportOut.model_validate(r) for r in items], total=len(items)
    )


@router.get("/{report_id}/download")
async def download_report(
    report_id: str, db: DbSession, user: CurrentUser
) -> Response:
    try:
        data, media, filename = await report_service.get_report_bytes(db, report_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Report not found") from exc
    return Response(
        content=data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{report_id}", response_model=ReportOut)
async def get_report(
    report_id: str, db: DbSession, user: CurrentUser
) -> ReportOut:
    report = await report_service.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return ReportOut.model_validate(report)
