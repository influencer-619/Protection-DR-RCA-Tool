"""Parent Incident APIs — explicit link / unlink / late attach (no time-only merge)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import IncidentMember, User
from app.schemas.incidents import (
    IncidentCreate,
    IncidentLateAttachRequest,
    IncidentLinkRequest,
    IncidentOut,
    IncidentUnlinkRequest,
)
from app.services import event_service, incident_service

router = APIRouter(prefix="/incidents", tags=["incidents"])


def _out(data: dict) -> IncidentOut:
    return IncidentOut.model_validate(data)


@router.post("", response_model=IncidentOut)
async def create_incident(
    body: IncidentCreate,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> IncidentOut:
    try:
        inc = await incident_service.create_incident(
            db,
            mode=body.mode,
            correlation_reason=body.correlation_reason,
            correlation_detail=body.correlation_detail,
            title=body.title,
            description=body.description,
            created_by=user.id,
            request_id=getattr(request.state, "request_id", None),
        )
        for eid in body.event_ids or []:
            ev = await event_service.get_event(db, eid)
            if ev is None:
                raise HTTPException(status_code=404, detail=f"Event not found: {eid}")
            await incident_service.link_event(
                db,
                inc,
                ev,
                role="SOURCE",
                link_reason=body.correlation_reason,
                link_detail=body.correlation_detail,
                linked_by=user.id,
                request_id=getattr(request.state, "request_id", None),
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return _out(await incident_service.incident_to_dict(db, inc))


@router.get("/by-event/{event_id}", response_model=Optional[IncidentOut])
async def incident_for_event(
    event_id: str, db: DbSession, user: CurrentUser
) -> Optional[IncidentOut]:
    """Return the active incident that includes this event, if any."""
    ev = await event_service.get_event(db, event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")
    row = (
        await db.execute(
            select(IncidentMember).where(
                IncidentMember.event_id == ev.id,
                IncidentMember.active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    inc = await incident_service.get_incident(db, row.incident_id)
    if inc is None:
        return None
    return _out(await incident_service.incident_to_dict(db, inc))


@router.get("/{incident_id}", response_model=IncidentOut)
async def get_incident(
    incident_id: str, db: DbSession, user: CurrentUser
) -> IncidentOut:
    inc = await incident_service.get_incident(db, incident_id)
    if inc is None:
        inc = await incident_service.get_incident_by_code(db, incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    return _out(await incident_service.incident_to_dict(db, inc))


@router.post("/{incident_id}/link", response_model=IncidentOut)
async def link_event(
    incident_id: str,
    body: IncidentLinkRequest,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> IncidentOut:
    inc = await incident_service.get_incident(db, incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    ev = await event_service.get_event(db, body.event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")
    try:
        await incident_service.link_event(
            db,
            inc,
            ev,
            role=body.role,
            link_reason=body.link_reason,
            link_detail=body.link_detail,
            linked_by=user.id,
            request_id=getattr(request.state, "request_id", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return _out(await incident_service.incident_to_dict(db, inc))


@router.post("/{incident_id}/unlink", response_model=IncidentOut)
async def unlink_event(
    incident_id: str,
    body: IncidentUnlinkRequest,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> IncidentOut:
    inc = await incident_service.get_incident(db, incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    ev = await event_service.get_event(db, body.event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")
    await incident_service.unlink_event(
        db,
        inc,
        ev,
        unlinked_by=user.id,
        detail=body.detail,
        request_id=getattr(request.state, "request_id", None),
    )
    await db.commit()
    return _out(await incident_service.incident_to_dict(db, inc))


@router.post("/{incident_id}/attach-late", response_model=IncidentOut)
async def attach_late_dr(
    incident_id: str,
    body: IncidentLateAttachRequest,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> IncidentOut:
    """Attach a late-arriving DR event — requires explicit LATE_DR_ATTACH reason."""
    inc = await incident_service.get_incident(db, incident_id)
    if inc is None:
        raise HTTPException(status_code=404, detail="Incident not found")
    if str(inc.status or "").upper() == "SPLIT":
        raise HTTPException(status_code=400, detail="Incident is SPLIT — create a new incident")
    ev = await event_service.get_event(db, body.event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="Event not found")
    try:
        await incident_service.attach_late_event(
            db,
            inc,
            ev,
            role=body.role,
            detail=body.detail,
            linked_by=user.id,
            request_id=getattr(request.state, "request_id", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return _out(await incident_service.incident_to_dict(db, inc))
