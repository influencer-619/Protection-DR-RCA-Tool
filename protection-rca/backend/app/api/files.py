"""File upload API — immutable, hashed storage."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from sqlalchemy import select

from app.core.config import get_settings
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
    end_label: Optional[str] = Form(None),
) -> list[EventFileOut]:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    label = (end_label or "LOCAL").strip().upper() or "LOCAL"
    if label not in ("LOCAL", "REMOTE") and not label.startswith("REMOTE"):
        raise HTTPException(status_code=400, detail="end_label must be LOCAL or REMOTE")
    file_meta = {"end_label": label}
    allowed = set(get_settings().allowed_extensions)
    stored: list[EventFileOut] = []
    skipped: list[str] = []
    for f in files:
        name = f.filename or "upload.bin"
        ext = Path(name).suffix.lower()
        if ext not in allowed:
            skipped.append(f"{name} ({ext or 'no extension'})")
            continue
        try:
            efs = await file_service.store_event_file(
                db,
                event,
                f,
                source_type=source_type,
                uploaded_by=user.id,
                request_id=getattr(request.state, "request_id", None),
                file_metadata=file_meta,
            )
        except HTTPException as exc:
            # Do not fail the whole DIGSI/MiCOM folder drop for one side file
            if exc.status_code in (
                status.HTTP_400_BAD_REQUEST,
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            ):
                skipped.append(f"{name}: {exc.detail}")
                continue
            raise
        stored.extend(EventFileOut.model_validate(ef) for ef in efs)
    if not stored:
        detail = "No allowed files uploaded"
        if skipped:
            detail += " — skipped: " + "; ".join(skipped[:8])
        raise HTTPException(status_code=400, detail=detail)
    return stored
