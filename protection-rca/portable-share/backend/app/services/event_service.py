"""Event CRUD service."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event
from app.schemas.events import EventCreate, EventUpdate
from app.services.audit_service import write_audit


async def create_event(
    db: AsyncSession,
    data: EventCreate,
    *,
    engineer_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Event:
    payload = data.model_dump(exclude_unset=True)
    labels = {
        k: payload.pop(k)
        for k in (
            "substation_name",
            "bay_name",
            "relay_tag",
            "breaker_tag",
            "asset_name",
        )
        if k in payload
    }
    extra = dict(payload.pop("extra", None) or {})
    if labels:
        extra.setdefault("plant_labels", {})
        extra["plant_labels"].update({k: v for k, v in labels.items() if v})
        for k, v in labels.items():
            if v:
                extra[k] = v
    if "event_id" in payload and not payload["event_id"]:
        payload.pop("event_id")
    event = Event(
        **payload,
        engineer_id=engineer_id,
        status="UPLOADED",
        extra=extra or None,
    )
    db.add(event)
    await db.flush()
    await write_audit(
        db,
        action="CREATE",
        user_id=engineer_id,
        object_type="Event",
        object_id=event.id,
        new_value={"event_id": event.event_id, "status": event.status},
        request_id=request_id,
    )
    return event


async def get_event(db: AsyncSession, event_id: str) -> Optional[Event]:
    # Accept either PK id or business event_id
    result = await db.execute(
        select(Event).where((Event.id == event_id) | (Event.event_id == event_id))
    )
    return result.scalar_one_or_none()


async def list_events(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    status: Optional[str] = None,
    substation_id: Optional[str] = None,
    decision_state: Optional[str] = None,
    data_quality: Optional[str] = None,
    queue: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> tuple[list[Event], int]:
    from datetime import datetime

    q = select(Event)
    cq = select(func.count()).select_from(Event)

    if queue == "awaiting_analysis":
        q = q.where(Event.status.in_(("UPLOADED", "PARSED", "QUEUED", "ANALYSING")))
        cq = cq.where(Event.status.in_(("UPLOADED", "PARSED", "QUEUED", "ANALYSING")))
    elif queue == "awaiting_review":
        q = q.where(Event.status.in_(("REVIEW", "AWAITING_REVIEW", "ANALYSED")))
        cq = cq.where(Event.status.in_(("REVIEW", "AWAITING_REVIEW", "ANALYSED")))
    elif queue == "rca_inconclusive":
        q = q.where(Event.decision_state.in_(("INCONCLUSIVE", "DATA_INSUFFICIENT")))
        cq = cq.where(Event.decision_state.in_(("INCONCLUSIVE", "DATA_INSUFFICIENT")))
    elif queue == "parser_dq_issues":
        q = q.where(Event.data_quality.in_(("WARNING", "POOR", "INVALID")))
        cq = cq.where(Event.data_quality.in_(("WARNING", "POOR", "INVALID")))
    elif queue == "high_severity":
        # Join via consistency findings severity
        from app.models import ConsistencyFinding

        subq = (
            select(ConsistencyFinding.event_id)
            .where(ConsistencyFinding.severity.in_(("HIGH", "CRITICAL")))
            .distinct()
        )
        q = q.where(Event.id.in_(subq))
        cq = cq.where(Event.id.in_(subq))
    elif queue == "consistency_issues":
        from app.models import ConsistencyFinding

        subq = (
            select(ConsistencyFinding.event_id)
            .where(ConsistencyFinding.status == "INCONSISTENT")
            .distinct()
        )
        q = q.where(Event.id.in_(subq))
        cq = cq.where(Event.id.in_(subq))
    elif queue == "completed_reports":
        from app.models import Report

        subq = (
            select(Report.event_id)
            .where(Report.status.in_(("READY", "PUBLISHED", "COMPLETE", "GENERATED")))
            .distinct()
        )
        q = q.where(Event.id.in_(subq))
        cq = cq.where(Event.id.in_(subq))

    if status:
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if len(statuses) == 1:
            q = q.where(Event.status == statuses[0])
            cq = cq.where(Event.status == statuses[0])
        elif statuses:
            q = q.where(Event.status.in_(statuses))
            cq = cq.where(Event.status.in_(statuses))
    if substation_id:
        q = q.where(Event.substation_id == substation_id)
        cq = cq.where(Event.substation_id == substation_id)
    if decision_state:
        q = q.where(Event.decision_state == decision_state)
        cq = cq.where(Event.decision_state == decision_state)
    if data_quality:
        qualities = [s.strip() for s in data_quality.split(",") if s.strip()]
        if qualities:
            q = q.where(Event.data_quality.in_(qualities))
            cq = cq.where(Event.data_quality.in_(qualities))

    def _parse_dt(raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                return datetime.strptime(raw[:16], "%Y-%m-%dT%H:%M")
            except ValueError:
                return None

    df = _parse_dt(date_from)
    dt = _parse_dt(date_to)
    if df is not None:
        q = q.where(
            (Event.event_datetime >= df) | ((Event.event_datetime.is_(None)) & (Event.created_at >= df))
        )
        cq = cq.where(
            (Event.event_datetime >= df) | ((Event.event_datetime.is_(None)) & (Event.created_at >= df))
        )
    if dt is not None:
        q = q.where(
            (Event.event_datetime <= dt) | ((Event.event_datetime.is_(None)) & (Event.created_at <= dt))
        )
        cq = cq.where(
            (Event.event_datetime <= dt) | ((Event.event_datetime.is_(None)) & (Event.created_at <= dt))
        )

    total = (await db.execute(cq)).scalar_one()
    rows = (
        await db.execute(
            q.order_by(Event.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def update_event(
    db: AsyncSession,
    event: Event,
    data: EventUpdate,
    *,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Event:
    payload = data.model_dump(exclude_unset=True)
    label_keys = (
        "substation_name",
        "bay_name",
        "relay_tag",
        "breaker_tag",
        "asset_name",
    )
    labels = {k: payload.pop(k) for k in label_keys if k in payload}
    old = {
        "status": event.status,
        "description": event.description,
        "plant": {
            k: (event.extra or {}).get(k) if isinstance(event.extra, dict) else None
            for k in label_keys
        },
    }
    for key, value in payload.items():
        if key == "extra" and isinstance(value, dict):
            merged = dict(event.extra) if isinstance(event.extra, dict) else {}
            merged.update(value)
            event.extra = merged
        else:
            setattr(event, key, value)
    if labels:
        extra = dict(event.extra) if isinstance(event.extra, dict) else {}
        plant = dict(extra.get("plant_labels") or {}) if isinstance(extra.get("plant_labels"), dict) else {}
        for k, v in labels.items():
            text = (v or "").strip() if isinstance(v, str) else v
            if text:
                extra[k] = text
                plant[k] = text
            else:
                extra.pop(k, None)
                plant.pop(k, None)
        extra["plant_labels"] = plant
        event.extra = extra
    await db.flush()
    await write_audit(
        db,
        action="UPDATE",
        user_id=user_id,
        object_type="Event",
        object_id=event.id,
        old_value=old,
        new_value=data.model_dump(exclude_unset=True),
        request_id=request_id,
    )
    await db.refresh(event)
    return event


async def verify_active_setting_group(
    db: AsyncSession,
    event: Event,
    *,
    note: Optional[str] = None,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Event:
    """Record engineer confirmation that the bound setting group was active."""
    from datetime import datetime, timezone

    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    has_settings = bool(
        extra.get("setting_source")
        or extra.get("setting_param_count")
        or extra.get("setting_group")
        or extra.get("settings_file_verification_note")
    )
    if not has_settings:
        raise ValueError("No settings package loaded for this event — upload settings first")

    old = {
        "active_group_status": extra.get("active_group_status"),
        "engineer_verified_active_group": extra.get("engineer_verified_active_group"),
    }
    extra["engineer_verified_active_group"] = True
    extra["active_group_status"] = "VERIFIED"
    extra["active_group_verified_at"] = datetime.now(timezone.utc).isoformat()
    if user_id:
        extra["active_group_verified_by"] = user_id
    if note:
        extra["active_group_verification_note"] = note.strip()[:1000]
    else:
        extra.setdefault(
            "active_group_verification_note",
            "Engineer confirmed active setting group for this event",
        )
    event.extra = extra
    await db.flush()
    await write_audit(
        db,
        action="VERIFY_ACTIVE_SETTINGS",
        user_id=user_id,
        object_type="Event",
        object_id=event.id,
        old_value=old,
        new_value={
            "active_group_status": "VERIFIED",
            "engineer_verified_active_group": True,
            "note": extra.get("active_group_verification_note"),
        },
        request_id=request_id,
    )
    # Reload server-onupdate columns (updated_at) so EventOut validation is sync-safe.
    await db.refresh(event)
    return event


async def approve_settings_file(
    db: AsyncSession,
    event: Event,
    *,
    note: Optional[str] = None,
    also_verify_active_group: bool = True,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Event:
    """Record engineer approval of the uploaded settings package for this event."""
    from datetime import datetime, timezone

    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    has_settings = bool(
        extra.get("setting_source")
        or extra.get("setting_param_count")
        or extra.get("setting_group")
        or extra.get("setting_file")
        or extra.get("settings_file_verification_note")
    )
    if not has_settings:
        raise ValueError("No settings package loaded for this event — upload settings first")

    old = {
        "setting_approval": extra.get("setting_approval"),
        "settings_engineer_approved": extra.get("settings_engineer_approved"),
        "active_group_status": extra.get("active_group_status"),
    }
    extra["settings_engineer_approved"] = True
    extra["setting_approval"] = "APPROVED"
    extra["settings_approved_at"] = datetime.now(timezone.utc).isoformat()
    if user_id:
        extra["settings_approved_by"] = user_id
    if note:
        extra["settings_approval_note"] = note.strip()[:1000]
    else:
        extra.setdefault(
            "settings_approval_note",
            "Engineer approved uploaded settings package for this event",
        )
    # Promote generic uploads to approved-base semantics for hierarchy display
    src = str(extra.get("setting_source") or "")
    if src.upper() in ("", "NOT VERIFIED", "RELAY_CONFIGURATION", "UPLOADED"):
        extra["setting_source"] = "APPROVED_RELAY_BASE"

    if also_verify_active_group:
        extra["engineer_verified_active_group"] = True
        extra["active_group_status"] = "VERIFIED"
        extra["active_group_verified_at"] = datetime.now(timezone.utc).isoformat()
        if user_id:
            extra["active_group_verified_by"] = user_id
        if note:
            extra["active_group_verification_note"] = note.strip()[:1000]
        else:
            extra.setdefault(
                "active_group_verification_note",
                "Active group confirmed with settings file approval",
            )

    event.extra = extra
    await db.flush()
    await write_audit(
        db,
        action="APPROVE_SETTINGS_FILE",
        user_id=user_id,
        object_type="Event",
        object_id=event.id,
        old_value=old,
        new_value={
            "setting_approval": "APPROVED",
            "settings_engineer_approved": True,
            "also_verify_active_group": also_verify_active_group,
            "active_group_status": extra.get("active_group_status"),
            "note": extra.get("settings_approval_note"),
        },
        request_id=request_id,
    )
    # Reload server-onupdate columns (updated_at) so EventOut validation is sync-safe.
    await db.refresh(event)
    return event


async def delete_event(
    db: AsyncSession,
    event: Event,
    *,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    """Delete event and cascaded analysis artefacts. Audited. Original files remain in object storage (immutable)."""
    snapshot = {
        "id": event.id,
        "event_id": event.event_id,
        "status": event.status,
        "decision_state": event.decision_state,
        "data_quality": event.data_quality,
    }
    await write_audit(
        db,
        action="DELETE",
        user_id=user_id,
        object_type="Event",
        object_id=event.id,
        old_value=snapshot,
        new_value=None,
        request_id=request_id,
    )
    await db.delete(event)
    await db.flush()
