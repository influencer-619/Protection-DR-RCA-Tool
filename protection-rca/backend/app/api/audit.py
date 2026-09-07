"""Audit log API."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from app.core.security import Role
from app.models import User
from app.dependencies.auth import DbSession, require_role
from app.schemas.audit import AuditListResponse, AuditLogOut
from app.services import audit_service

router = APIRouter(prefix="/api/audit", tags=["audit"])


class AuditClearResponse(BaseModel):
    deleted: int


@router.get("", response_model=AuditListResponse)
async def list_audit_logs(
    db: DbSession,
    user: User = Depends(require_role(Role.APPROVER)),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    action: Optional[str] = None,
    object_type: Optional[str] = None,
) -> AuditListResponse:
    items, total = await audit_service.list_audit(
        db, page=page, page_size=page_size, action=action, object_type=object_type
    )
    return AuditListResponse(
        items=[AuditLogOut.model_validate(i) for i in items], total=total
    )


@router.delete("", response_model=AuditClearResponse)
async def clear_audit_logs(
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> AuditClearResponse:
    deleted = await audit_service.clear_audit(
        db,
        user_id=user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )
    return AuditClearResponse(deleted=deleted)
