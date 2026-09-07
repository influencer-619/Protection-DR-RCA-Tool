"""Audit logging service."""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog


async def write_audit(
    db: AsyncSession,
    *,
    action: str,
    user_id: Optional[str] = None,
    object_type: Optional[str] = None,
    object_id: Optional[str] = None,
    old_value: Optional[dict[str, Any]] = None,
    new_value: Optional[dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> AuditLog:
    entry = AuditLog(
        user_id=user_id,
        action=action,
        object_type=object_type,
        object_id=object_id,
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        metadata_json=metadata,
    )
    db.add(entry)
    await db.flush()
    return entry


async def list_audit(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 50,
    action: Optional[str] = None,
    object_type: Optional[str] = None,
) -> tuple[list[AuditLog], int]:
    q = select(AuditLog)
    count_q = select(func.count()).select_from(AuditLog)
    if action:
        q = q.where(AuditLog.action == action)
        count_q = count_q.where(AuditLog.action == action)
    if object_type:
        q = q.where(AuditLog.object_type == object_type)
        count_q = count_q.where(AuditLog.object_type == object_type)
    total = (await db.execute(count_q)).scalar_one()
    q = (
        q.order_by(AuditLog.timestamp.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = (await db.execute(q)).scalars().all()
    return list(rows), int(total)


async def clear_audit(
    db: AsyncSession,
    *,
    user_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    request_id: Optional[str] = None,
) -> int:
    """Delete all audit rows, then record a single CLEAR entry for the actor."""
    total = (await db.execute(select(func.count()).select_from(AuditLog))).scalar_one()
    deleted = int(total)
    await db.execute(delete(AuditLog))
    await db.flush()
    await write_audit(
        db,
        action="CLEAR",
        user_id=user_id,
        object_type="audit_log",
        new_value={"deleted_count": deleted},
        ip_address=ip_address,
        user_agent=user_agent,
        request_id=request_id,
        metadata={"deleted_count": deleted},
    )
    return deleted
