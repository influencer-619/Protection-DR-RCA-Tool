"""Relay settings API."""

from __future__ import annotations

from typing import Annotated

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.core.security import Role
from app.models import User
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.schemas.settings import SettingCreate, SettingListResponse, SettingOut
from app.services import settings_service

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.post("", response_model=SettingOut, status_code=status.HTTP_201_CREATED)
async def create_setting(
    body: SettingCreate,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.PROTECTION_ENGINEER)),
) -> SettingOut:
    setting = await settings_service.create_setting(
        db,
        body,
        user_id=user.id,
        request_id=getattr(request.state, "request_id", None),
    )
    return SettingOut.model_validate(setting)


@router.get("", response_model=SettingListResponse)
async def list_settings(
    db: DbSession,
    user: CurrentUser,
    relay_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
) -> SettingListResponse:
    items, total = await settings_service.list_settings(
        db, relay_id=relay_id, page=page, page_size=page_size
    )
    return SettingListResponse(
        items=[SettingOut.model_validate(s) for s in items], total=total
    )


@router.get("/{setting_id}", response_model=SettingOut)
async def get_setting(
    setting_id: str, db: DbSession, user: CurrentUser
) -> SettingOut:
    setting = await settings_service.get_setting(db, setting_id)
    if setting is None:
        raise HTTPException(status_code=404, detail="Setting not found")
    return SettingOut.model_validate(setting)
