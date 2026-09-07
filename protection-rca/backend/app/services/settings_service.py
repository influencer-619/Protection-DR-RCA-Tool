"""Relay settings service."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Setting
from app.schemas.settings import SettingCreate
from app.services.audit_service import write_audit


async def create_setting(
    db: AsyncSession,
    data: SettingCreate,
    *,
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Setting:
    setting = Setting(**data.model_dump(exclude_unset=True))
    db.add(setting)
    await db.flush()
    await write_audit(
        db,
        action="CREATE",
        user_id=user_id,
        object_type="Setting",
        object_id=setting.id,
        new_value={"parameter": setting.parameter, "relay_id": setting.relay_id},
        request_id=request_id,
    )
    return setting


async def list_settings(
    db: AsyncSession,
    *,
    relay_id: Optional[str] = None,
    page: int = 1,
    page_size: int = 100,
) -> tuple[list[Setting], int]:
    q = select(Setting)
    cq = select(func.count()).select_from(Setting)
    if relay_id:
        q = q.where(Setting.relay_id == relay_id)
        cq = cq.where(Setting.relay_id == relay_id)
    total = (await db.execute(cq)).scalar_one()
    rows = (
        await db.execute(
            q.order_by(Setting.parameter)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), int(total)


async def get_setting(db: AsyncSession, setting_id: str) -> Optional[Setting]:
    result = await db.execute(
        select(Setting).where(
            (Setting.id == setting_id) | (Setting.setting_id == setting_id)
        )
    )
    return result.scalar_one_or_none()
