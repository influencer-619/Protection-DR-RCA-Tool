"""Events API — CRUD."""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select

from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import ProtectionOperation, User
from app.schemas.events import (
    ApproveSettingsFileRequest,
    EventCreate,
    EventListResponse,
    EventOut,
    EventUpdate,
    VerifyActiveSettingsRequest,
)
from app.services import event_service

router = APIRouter(prefix="/api/events", tags=["events"])


def _event_out(event, *, protection_summary: Optional[str] = None) -> EventOut:
    base = EventOut.model_validate(event)
    extra = event.extra if isinstance(event.extra, dict) else {}
    plant = extra.get("plant_labels") if isinstance(extra.get("plant_labels"), dict) else {}
    combined = (
        bool(extra.get("combined_ready"))
        or isinstance(extra.get("combined_analysis"), dict)
    )
    # Combined events: prefer dual-end plant_labels over single-IED CFG tags
    def _label(key: str):
        if combined:
            return plant.get(key) or extra.get(key)
        return extra.get(key) or plant.get(key)

    prot = protection_summary if protection_summary is not None else extra.get("protection_summary")
    if isinstance(prot, str) and not prot.strip():
        prot = None
    return base.model_copy(
        update={
            "substation_name": _label("substation_name"),
            "bay_name": _label("bay_name"),
            "relay_tag": _label("relay_tag"),
            "breaker_tag": _label("breaker_tag"),
            "asset_name": _label("asset_name"),
            "fault_type": extra.get("fault_type"),
            "event_class": extra.get("event_class"),
            "fault_display": extra.get("fault_display") or extra.get("fault_type"),
            "severity_summary": extra.get("severity_summary"),
            "protection_summary": prot,
        }
    )


async def _protection_by_event_ids(db, event_ids: list[str]) -> dict[str, str]:
    if not event_ids:
        return {}
    rows = (
        await db.execute(
            select(
                ProtectionOperation.event_id,
                ProtectionOperation.element,
                ProtectionOperation.function_code,
            ).where(
                ProtectionOperation.event_id.in_(event_ids),
                ProtectionOperation.asserted.is_(True),
                ProtectionOperation.operation_type.in_(
                    ("TRIP", "trip", "PICKUP", "pickup")
                ),
            )
        )
    ).all()
    by_id: dict[str, set[str]] = defaultdict(set)
    for eid, element, fcode in rows:
        code = str(element or fcode or "").strip()
        if code and code.upper() != "UNKNOWN":
            by_id[str(eid)].add(code)
    out: dict[str, str] = {}
    for eid, codes in by_id.items():
        ordered = sorted(
            codes, key=lambda c: (0 if any(ch.isdigit() for ch in c) else 1, c.upper())
        )
        out[eid] = ", ".join(ordered)
    return out


@router.post("", response_model=EventOut, status_code=status.HTTP_201_CREATED)
async def create_event(
    body: EventCreate,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> EventOut:
    if not body.relay_id:
        raise HTTPException(
            status_code=400,
            detail="relay_id (IED) is required — create events from Plant → IED",
        )
    event = await event_service.create_event(
        db,
        body,
        engineer_id=user.id,
        request_id=getattr(request.state, "request_id", None),
    )
    return _event_out(event)


@router.get("", response_model=EventListResponse)
async def list_events(
    db: DbSession,
    user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    status_filter: Optional[str] = Query(None, alias="status"),
    substation_id: Optional[str] = None,
    relay_id: Optional[str] = None,
    unmapped: Optional[bool] = None,
    decision_state: Optional[str] = None,
    data_quality: Optional[str] = None,
    queue: Optional[str] = None,
    date_from: Optional[str] = Query(None, description="ISO datetime lower bound"),
    date_to: Optional[str] = Query(None, description="ISO datetime upper bound"),
) -> EventListResponse:
    items, total = await event_service.list_events(
        db,
        page=page,
        page_size=page_size,
        status=status_filter,
        substation_id=substation_id,
        relay_id=relay_id,
        unmapped=unmapped,
        decision_state=decision_state,
        data_quality=data_quality,
        queue=queue,
        date_from=date_from,
        date_to=date_to,
    )
    need_ids = []
    for e in items:
        extra = e.extra if isinstance(e.extra, dict) else {}
        if not extra.get("protection_summary"):
            need_ids.append(e.id)
    prot_map = await _protection_by_event_ids(db, need_ids)
    return EventListResponse(
        items=[
            _event_out(
                e,
                protection_summary=(
                    (e.extra or {}).get("protection_summary")
                    if isinstance(e.extra, dict) and e.extra.get("protection_summary")
                    else prot_map.get(e.id)
                ),
            )
            for e in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{event_id}", response_model=EventOut)
async def get_event(event_id: str, db: DbSession, user: CurrentUser) -> EventOut:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    # Heal sticky FAILED / ANALYZING when artefacts exist or the queue was orphaned.
    from app.services import analysis_service as _analysis_svc

    if str(event.status or "").upper() in ("FAILED", "ANALYZING", "PENDING"):
        await _analysis_svc.heal_stuck_analysis(db, event)
        await db.commit()
    extra = event.extra if isinstance(event.extra, dict) else {}
    prot = extra.get("protection_summary")
    if not prot:
        prot_map = await _protection_by_event_ids(db, [event.id])
        prot = prot_map.get(event.id)
    return _event_out(event, protection_summary=prot if isinstance(prot, str) else None)


@router.patch("/{event_id}", response_model=EventOut)
async def update_event(
    event_id: str,
    body: EventUpdate,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> EventOut:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    event = await event_service.update_event(
        db,
        event,
        body,
        user_id=user.id,
        request_id=getattr(request.state, "request_id", None),
    )
    return _event_out(event)


@router.post("/{event_id}/verify-active-settings", response_model=EventOut)
async def verify_active_settings(
    event_id: str,
    body: VerifyActiveSettingsRequest,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> EventOut:
    """Engineer confirms the uploaded setting group was active for this disturbance."""
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="confirmed must be true")
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    try:
        event = await event_service.verify_active_setting_group(
            db,
            event,
            note=body.note,
            user_id=user.id,
            request_id=getattr(request.state, "request_id", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _event_out(event)


@router.post("/{event_id}/approve-settings", response_model=EventOut)
async def approve_settings_file(
    event_id: str,
    body: ApproveSettingsFileRequest,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> EventOut:
    """Engineer approves the uploaded settings package (optional active-group confirm)."""
    if not body.confirmed:
        raise HTTPException(status_code=400, detail="confirmed must be true")
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    try:
        event = await event_service.approve_settings_file(
            db,
            event,
            note=body.note,
            also_verify_active_group=body.also_verify_active_group,
            user_id=user.id,
            request_id=getattr(request.state, "request_id", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _event_out(event)


@router.delete("/{event_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_event(
    event_id: str,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> None:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    await event_service.delete_event(
        db,
        event,
        user_id=user.id,
        request_id=getattr(request.state, "request_id", None),
    )
