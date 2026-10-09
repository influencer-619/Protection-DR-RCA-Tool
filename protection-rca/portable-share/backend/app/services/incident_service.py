"""Parent Incident correlation — explicit link/unlink; never timestamp-only merge.

Stage E (GAP-DATA-006): multi-IED incidents link original events; combined Events
remain valid. Late DR attach requires engineer reason + incident id.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models import Event, EventCounter, Incident, IncidentMember
from app.services.audit_service import write_audit

# Allowed correlation / link reasons — TIMESTAMP_ONLY is intentionally absent.
ALLOWED_REASONS = frozenset(
    {
        "COMBINED_CASCADE",
        "COMBINED_LINE_MULTI_END",
        "ENGINEER_LINK",
        "LATE_DR_ATTACH",
        "SPLIT_UNLINK",
        "COMBINED_EVENT_MEMBER",
    }
)

FORBIDDEN_AUTO_REASONS = frozenset(
    {
        "TIMESTAMP_ONLY",
        "TIMESTAMP_WINDOW",
        "AUTO_TIME_CORRELATE",
        "TIME_PROXIMITY",
        "AUTO_MERGE",
    }
)

ALLOWED_ROLES = frozenset(
    {
        "SOURCE",
        "COMBINED",
        "LOCAL",
        "REMOTE",
        "INITIATOR",
        "BACKUP",
        "LATE_ATTACH",
    }
)

_INCIDENT_RE = re.compile(r"^INC-(\d{4})-(\d+)$")


def normalize_reason(reason: Optional[str]) -> str:
    return str(reason or "").strip().upper().replace(" ", "_").replace("-", "_")


def validate_correlation_reason(reason: Optional[str]) -> str:
    """Raise ValueError if reason is missing, forbidden, or not in allow-list."""
    r = normalize_reason(reason)
    if not r:
        raise ValueError(
            "correlation_reason is required — timestamp-only merge is not allowed"
        )
    if r in FORBIDDEN_AUTO_REASONS or "TIMESTAMP" in r and "ONLY" in r:
        raise ValueError(
            f"correlation_reason '{r}' is not allowed — do not merge by time window alone"
        )
    if r not in ALLOWED_REASONS:
        raise ValueError(
            f"correlation_reason '{r}' unknown — use one of: "
            + ", ".join(sorted(ALLOWED_REASONS))
        )
    return r


def validate_member_role(role: Optional[str]) -> str:
    r = str(role or "SOURCE").strip().upper()
    if r not in ALLOWED_ROLES:
        raise ValueError(f"role must be one of: {', '.join(sorted(ALLOWED_ROLES))}")
    return r


def format_incident_code(year: int, seq: int) -> str:
    return f"INC-{year}-{seq:05d}"


async def _highest_incident(db: AsyncSession, year: int) -> int:
    rows = (
        await db.execute(select(Incident.incident_code).where(Incident.incident_code.like(f"INC-{year}-%")))
    ).scalars().all()
    top = 0
    for code in rows:
        m = _INCIDENT_RE.match(str(code or ""))
        if m and int(m.group(1)) == year:
            top = max(top, int(m.group(2)))
    return top


async def next_incident_code(db: AsyncSession, year: Optional[int] = None) -> str:
    year = year or datetime.now().year
    series = f"INC-{year}"
    for _ in range(2):
        res = await db.execute(
            update(EventCounter)
            .where(EventCounter.series == series)
            .values(value=EventCounter.value + 1)
            .returning(EventCounter.value)
        )
        seq = res.scalar_one_or_none()
        if seq is not None:
            candidate = format_incident_code(year, int(seq))
            clash = await db.execute(
                select(Incident.id).where(Incident.incident_code == candidate)
            )
            if clash.first() is None:
                return candidate
            top = await _highest_incident(db, year)
            await db.execute(
                update(EventCounter).where(EventCounter.series == series).values(value=top + 1)
            )
            return format_incident_code(year, top + 1)
        db.add(EventCounter(series=series, value=await _highest_incident(db, year)))
        await db.flush()
    raise RuntimeError("Could not allocate incident code")


def _stamp_event_incident(event: Event, incident: Incident, *, role: str) -> None:
    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    extra["incident"] = {
        "incident_id": incident.id,
        "incident_code": incident.incident_code,
        "mode": incident.mode,
        "role": role,
        "correlation_reason": incident.correlation_reason,
    }
    event.extra = extra
    try:
        flag_modified(event, "extra")
    except Exception:  # noqa: BLE001
        pass


def _clear_event_incident_stamp(event: Event) -> None:
    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    if "incident" in extra:
        extra.pop("incident", None)
        event.extra = extra
        try:
            flag_modified(event, "extra")
        except Exception:  # noqa: BLE001
            pass


async def create_incident(
    db: AsyncSession,
    *,
    mode: str = "MANUAL",
    correlation_reason: str,
    correlation_detail: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    created_by: Optional[str] = None,
    combined_event_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Incident:
    reason = validate_correlation_reason(correlation_reason)
    code = await next_incident_code(db)
    mode_n = str(mode or "MANUAL").strip().upper() or "MANUAL"
    inc = Incident(
        incident_code=code,
        title=title or f"Incident {code}",
        description=description,
        mode=mode_n,
        status="OPEN",
        correlation_reason=reason,
        correlation_detail=correlation_detail,
        created_by=created_by,
        combined_event_id=combined_event_id,
        extra={},
    )
    db.add(inc)
    await db.flush()
    await write_audit(
        db,
        action="INCIDENT_CREATE",
        user_id=created_by,
        object_type="Incident",
        object_id=inc.id,
        new_value={
            "incident_code": code,
            "mode": mode_n,
            "correlation_reason": reason,
        },
        request_id=request_id,
    )
    return inc


async def link_event(
    db: AsyncSession,
    incident: Incident,
    event: Event,
    *,
    role: str = "SOURCE",
    link_reason: str,
    link_detail: Optional[str] = None,
    linked_by: Optional[str] = None,
    request_id: Optional[str] = None,
) -> IncidentMember:
    reason = validate_correlation_reason(link_reason)
    role_n = validate_member_role(role)

    existing = (
        await db.execute(
            select(IncidentMember).where(
                IncidentMember.incident_id == incident.id,
                IncidentMember.event_id == event.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        if existing.active:
            existing.role = role_n
            existing.link_reason = reason
            if link_detail:
                existing.link_detail = link_detail
            await db.flush()
            _stamp_event_incident(event, incident, role=role_n)
            return existing
        existing.active = True
        existing.unlinked_at = None
        existing.role = role_n
        existing.link_reason = reason
        existing.link_detail = link_detail
        existing.linked_by = linked_by
        await db.flush()
        _stamp_event_incident(event, incident, role=role_n)
        return existing

    member = IncidentMember(
        incident_id=incident.id,
        event_id=event.id,
        role=role_n,
        link_reason=reason,
        link_detail=link_detail,
        linked_by=linked_by,
        active=True,
    )
    db.add(member)
    await db.flush()
    _stamp_event_incident(event, incident, role=role_n)
    await write_audit(
        db,
        action="INCIDENT_LINK",
        user_id=linked_by,
        object_type="IncidentMember",
        object_id=member.id,
        new_value={
            "incident_id": incident.id,
            "event_id": event.id,
            "role": role_n,
            "link_reason": reason,
        },
        request_id=request_id,
    )
    return member


async def unlink_event(
    db: AsyncSession,
    incident: Incident,
    event: Event,
    *,
    unlinked_by: Optional[str] = None,
    detail: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Optional[IncidentMember]:
    member = (
        await db.execute(
            select(IncidentMember).where(
                IncidentMember.incident_id == incident.id,
                IncidentMember.event_id == event.id,
                IncidentMember.active.is_(True),
            )
        )
    ).scalar_one_or_none()
    if member is None:
        return None
    member.active = False
    member.unlinked_at = datetime.now(timezone.utc)
    member.link_detail = (
        (member.link_detail or "") + (f" | unlink: {detail}" if detail else " | unlinked")
    ).strip(" |")
    await db.flush()
    _clear_event_incident_stamp(event)
    await write_audit(
        db,
        action="INCIDENT_UNLINK",
        user_id=unlinked_by,
        object_type="IncidentMember",
        object_id=member.id,
        new_value={"incident_id": incident.id, "event_id": event.id, "detail": detail},
        request_id=request_id,
    )
    return member


async def get_incident(db: AsyncSession, incident_id: str) -> Optional[Incident]:
    return (
        await db.execute(select(Incident).where(Incident.id == incident_id))
    ).scalar_one_or_none()


async def get_incident_by_code(db: AsyncSession, code: str) -> Optional[Incident]:
    return (
        await db.execute(select(Incident).where(Incident.incident_code == code))
    ).scalar_one_or_none()


async def list_active_members(
    db: AsyncSession, incident_id: str
) -> list[IncidentMember]:
    return list(
        (
            await db.execute(
                select(IncidentMember).where(
                    IncidentMember.incident_id == incident_id,
                    IncidentMember.active.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )


async def incident_to_dict(
    db: AsyncSession, incident: Incident
) -> dict[str, Any]:
    members = await list_active_members(db, incident.id)
    member_rows: list[dict[str, Any]] = []
    for m in members:
        ev = await db.get(Event, m.event_id)
        member_rows.append(
            {
                "member_id": m.id,
                "event_id": m.event_id,
                "event_code": ev.event_id if ev else None,
                "role": m.role,
                "link_reason": m.link_reason,
                "link_detail": m.link_detail,
                "linked_by": m.linked_by,
                "active": m.active,
            }
        )
    return {
        "id": incident.id,
        "incident_code": incident.incident_code,
        "title": incident.title,
        "description": incident.description,
        "mode": incident.mode,
        "status": incident.status,
        "correlation_reason": incident.correlation_reason,
        "correlation_detail": incident.correlation_detail,
        "combined_event_id": incident.combined_event_id,
        "created_by": incident.created_by,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
        "members": member_rows,
        "extra": incident.extra or {},
    }


async def attach_late_event(
    db: AsyncSession,
    incident: Incident,
    event: Event,
    *,
    role: str = "LATE_ATTACH",
    detail: Optional[str] = None,
    linked_by: Optional[str] = None,
    request_id: Optional[str] = None,
) -> IncidentMember:
    """Attach a late-arriving DR event to an existing incident (explicit reason)."""
    return await link_event(
        db,
        incident,
        event,
        role=role if role in ALLOWED_ROLES else "LATE_ATTACH",
        link_reason="LATE_DR_ATTACH",
        link_detail=detail or "Late-arriving disturbance record attached by engineer",
        linked_by=linked_by,
        request_id=request_id,
    )
