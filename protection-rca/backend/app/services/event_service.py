"""Event CRUD service."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, EventCounter
from app.schemas.events import EventCreate, EventUpdate
from app.services.audit_service import write_audit


EVENT_NUMBER_PREFIX = "EVT"
_EVENT_NUMBER_RE = re.compile(rf"^{EVENT_NUMBER_PREFIX}-(\d{{4}})-(\d+)$")
# Combined Cascade / Local-Remote: EVT-COMB-CASC-YYYY-NNNNN / EVT-COMB-LINE-YYYY-NNNNN
_COMBINED_KIND = {
    "CASCADE_LBB": "CASC",
    "LINE_MULTI_END": "LINE",
}
_COMBINED_NUMBER_RE = re.compile(
    rf"^{EVENT_NUMBER_PREFIX}-COMB-(CASC|LINE)-(\d{{4}})-(\d+)$"
)
_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def format_event_number(year: int, seq: int) -> str:
    return f"{EVENT_NUMBER_PREFIX}-{year}-{seq:05d}"


def format_combined_event_number(kind: str, year: int, seq: int) -> str:
    """kind is CASC or LINE."""
    return f"{EVENT_NUMBER_PREFIX}-COMB-{kind}-{year}-{seq:05d}"


def combined_kind_from_mode(mode: str | None) -> str:
    """Map analysis mode → event-number kind (CASC / LINE)."""
    m = (mode or "").strip().upper()
    if m in _COMBINED_KIND:
        return _COMBINED_KIND[m]
    if "CASCADE" in m or "LBB" in m:
        return "CASC"
    if "LINE" in m or "MULTI_END" in m:
        return "LINE"
    return "CASC"


async def _highest_used(db: AsyncSession, year: int) -> int:
    prefix = f"{EVENT_NUMBER_PREFIX}-{year}-"
    rows = (
        await db.execute(select(Event.event_id).where(Event.event_id.like(f"{prefix}%")))
    ).scalars()
    return max(
        (int(m.group(2)) for r in rows if (m := _EVENT_NUMBER_RE.match(r or ""))), default=0
    )


async def _highest_combined_used(db: AsyncSession, kind: str, year: int) -> int:
    prefix = f"{EVENT_NUMBER_PREFIX}-COMB-{kind}-{year}-"
    rows = (
        await db.execute(select(Event.event_id).where(Event.event_id.like(f"{prefix}%")))
    ).scalars()
    return max(
        (
            int(m.group(3))
            for r in rows
            if (m := _COMBINED_NUMBER_RE.match(r or "")) and m.group(1) == kind
        ),
        default=0,
    )


async def _allocate_series_number(
    db: AsyncSession,
    *,
    series: str,
    format_fn,
    highest_fn,
) -> str:
    """Bump EventCounter for ``series`` and return a unique formatted id."""
    for _ in range(2):
        res = await db.execute(
            update(EventCounter)
            .where(EventCounter.series == series)
            .values(value=EventCounter.value + 1)
            .returning(EventCounter.value)
        )
        seq = res.scalar_one_or_none()
        if seq is not None:
            candidate = format_fn(seq)
            clash = await db.execute(select(Event.id).where(Event.event_id == candidate))
            if clash.first() is None:
                return candidate
            top = await highest_fn()
            await db.execute(
                update(EventCounter).where(EventCounter.series == series).values(value=top + 1)
            )
            return format_fn(top + 1)
        db.add(EventCounter(series=series, value=await highest_fn()))
        await db.flush()
    raise RuntimeError(f"Could not allocate an event number for series {series}")


async def next_event_number(db: AsyncSession, year: Optional[int] = None) -> str:
    """Allocate the next EVT-<year>-<seq> number.

    The counter row is bumped with a single UPDATE so the database serialises
    concurrent allocations (row lock on PostgreSQL, write lock on SQLite).
    """
    year = year or datetime.now().year
    series = f"{EVENT_NUMBER_PREFIX}-{year}"
    return await _allocate_series_number(
        db,
        series=series,
        format_fn=lambda seq: format_event_number(year, seq),
        highest_fn=lambda: _highest_used(db, year),
    )


async def next_combined_event_number(
    db: AsyncSession,
    mode: str,
    year: Optional[int] = None,
) -> str:
    """Allocate EVT-COMB-CASC-YYYY-NNNNN or EVT-COMB-LINE-YYYY-NNNNN."""
    year = year or datetime.now().year
    kind = combined_kind_from_mode(mode)
    series = f"{EVENT_NUMBER_PREFIX}-COMB-{kind}-{year}"
    return await _allocate_series_number(
        db,
        series=series,
        format_fn=lambda seq: format_combined_event_number(kind, year, seq),
        highest_fn=lambda: _highest_combined_used(db, kind, year),
    )


async def renumber_legacy_events(db: AsyncSession) -> int:
    """Give events that still carry a random UUID as their number a readable EVT number."""
    rows = (
        await db.execute(select(Event).order_by(Event.created_at.asc(), Event.id.asc()))
    ).scalars().all()
    legacy = [e for e in rows if _UUID_RE.match(e.event_id or "")]
    for ev in legacy:
        created = ev.created_at or datetime.now()
        old = ev.event_id
        ev.event_id = await next_event_number(db, created.year)
        extra = dict(ev.extra or {})
        extra.setdefault("previous_event_id", old)
        ev.extra = extra
    if legacy:
        await db.flush()
    return len(legacy)


def _is_combined_event(ev: Event) -> bool:
    extra = ev.extra if isinstance(ev.extra, dict) else {}
    if extra.get("combined_ready") is True:
        return True
    ca = extra.get("combined_analysis")
    if isinstance(ca, dict) and (
        ca.get("primary_event_id") or ca.get("peer_event_id") or ca.get("mode")
    ):
        return True
    feeder = str(ev.feeder or "").upper()
    return feeder.startswith("COMBINED")


async def renumber_combined_events(db: AsyncSession) -> int:
    """Give combined Cascade/Line events a COMB-prefixed number if they still look single-IED."""
    rows = (
        await db.execute(select(Event).order_by(Event.created_at.asc(), Event.id.asc()))
    ).scalars().all()
    changed = 0
    for ev in rows:
        if not _is_combined_event(ev):
            continue
        code = str(ev.event_id or "")
        if _COMBINED_NUMBER_RE.match(code):
            continue
        extra = dict(ev.extra or {})
        ca = extra.get("combined_analysis") if isinstance(extra.get("combined_analysis"), dict) else {}
        mode = str(
            (ca or {}).get("mode")
            or extra.get("analysis_mode")
            or ("CASCADE_LBB" if "CASCADE" in str(ev.feeder or "").upper() else "LINE_MULTI_END")
        )
        created = ev.created_at or datetime.now()
        old = ev.event_id
        ev.event_id = await next_combined_event_number(db, mode, created.year)
        extra.setdefault("previous_event_id", old)
        extra["combined_event_number"] = True
        ev.extra = extra
        changed += 1
    if changed:
        await db.flush()
    return changed


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

    relay_id = payload.get("relay_id")
    if relay_id:
        from app.services.plant_service import resolve_ied_plant

        plant = await resolve_ied_plant(db, relay_id)
        payload["relay_id"] = plant["relay_id"]
        payload["bay_id"] = plant["bay_id"]
        payload["substation_id"] = plant["substation_id"]
        if not payload.get("feeder"):
            payload["feeder"] = plant["feeder"]
        if payload.get("nominal_voltage_kv") is None and plant.get("nominal_voltage_kv") is not None:
            payload["nominal_voltage_kv"] = plant["nominal_voltage_kv"]
        for k, v in plant["labels"].items():
            if v:
                labels.setdefault(k, v)
        extra["plant_mapped"] = True
        extra["plant_path"] = {
            "substation_id": plant["substation_id"],
            "bay_id": plant["bay_id"],
            "relay_id": plant["relay_id"],
            "feeder": plant["feeder"],
        }

    if labels:
        # Prefer explicit extra / plant_labels (e.g. combined LV+HV tags) over
        # single-IED defaults from the plant tree.
        extra.setdefault("plant_labels", {})
        for k, v in labels.items():
            if not v:
                continue
            extra["plant_labels"].setdefault(k, v)
            extra.setdefault(k, v)
    if payload.get("event_id"):
        payload["event_id"] = str(payload["event_id"]).strip()
    if not payload.get("event_id"):
        payload["event_id"] = await next_event_number(db)
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
    relay_id: Optional[str] = None,
    unmapped: Optional[bool] = None,
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
            .where(
                Report.status.in_(
                    ("READY", "PUBLISHED", "COMPLETE", "GENERATED", "FINAL")
                )
            )
            .distinct()
        )
        q = q.where(Event.id.in_(subq))
        cq = cq.where(Event.id.in_(subq))
    elif queue == "unmapped_plant":
        q = q.where(Event.relay_id.is_(None))
        cq = cq.where(Event.relay_id.is_(None))

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
    if relay_id:
        q = q.where(Event.relay_id == relay_id)
        cq = cq.where(Event.relay_id == relay_id)
    if unmapped is True:
        q = q.where(Event.relay_id.is_(None))
        cq = cq.where(Event.relay_id.is_(None))
    elif unmapped is False:
        q = q.where(Event.relay_id.is_not(None))
        cq = cq.where(Event.relay_id.is_not(None))
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


async def map_event_to_ied(
    db: AsyncSession,
    event: Event,
    relay_id: str,
    *,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Event:
    from app.services.plant_service import resolve_ied_plant

    plant = await resolve_ied_plant(db, relay_id)
    event.relay_id = plant["relay_id"]
    event.bay_id = plant["bay_id"]
    event.substation_id = plant["substation_id"]
    event.feeder = plant["feeder"]
    if event.nominal_voltage_kv is None and plant.get("nominal_voltage_kv") is not None:
        event.nominal_voltage_kv = plant["nominal_voltage_kv"]
    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    plant_labels = dict(extra.get("plant_labels") or {}) if isinstance(extra.get("plant_labels"), dict) else {}
    for k, v in plant["labels"].items():
        if v:
            extra[k] = v
            plant_labels[k] = v
    extra["plant_labels"] = plant_labels
    extra["plant_mapped"] = True
    extra["plant_path"] = {
        "substation_id": plant["substation_id"],
        "bay_id": plant["bay_id"],
        "relay_id": plant["relay_id"],
        "feeder": plant["feeder"],
    }
    event.extra = extra
    await db.flush()
    await write_audit(
        db,
        action="MAP_PLANT",
        user_id=user_id,
        object_type="Event",
        object_id=event.id,
        new_value={"relay_id": relay_id, "plant_path": extra["plant_path"]},
        request_id=request_id,
    )
    await db.refresh(event)
    return event


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
