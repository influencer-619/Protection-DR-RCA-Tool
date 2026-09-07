"""File upload API — immutable, hashed storage."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select

from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import EventFile, User
from app.schemas.files import EventFileOut
from app.services import event_service, file_service

router = APIRouter(prefix="/api/events", tags=["files"])


@router.get("/{event_id}/files", response_model=list[EventFileOut])
async def list_event_files(
    event_id: str, db: DbSession, user: CurrentUser
) -> list[EventFileOut]:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    rows = (
        await db.execute(
            select(EventFile)
            .where(EventFile.event_id == event.id)
            .order_by(EventFile.upload_timestamp.desc())
        )
    ).scalars().all()
    out: list[EventFileOut] = []
    dirty = False
    for r in rows:
        correct = file_service.corrected_source_type(r.original_filename or "", r.source_type)
        if correct != r.source_type:
            r.source_type = correct
            dirty = True
        out.append(EventFileOut.model_validate(r))
    if dirty:
        await db.commit()
    return out


@router.post("/{event_id}/files", response_model=list[EventFileOut])
async def upload_event_files(
    event_id: str,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
    files: list[UploadFile] = File(...),
    source_type: Optional[str] = Form(None),
) -> list[EventFileOut]:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    stored: list[EventFileOut] = []
    for f in files:
        efs = await file_service.store_event_file(
            db,
            event,
            f,
            source_type=source_type,
            uploaded_by=user.id,
            request_id=getattr(request.state, "request_id", None),
        )
        stored.extend(EventFileOut.model_validate(ef) for ef in efs)
    return stored
