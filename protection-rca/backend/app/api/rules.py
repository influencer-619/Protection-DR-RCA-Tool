"""Rule version registry API."""

from __future__ import annotations

from typing import Annotated

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import RuleVersion
from app.schemas.rules import RuleVersionCreate, RuleVersionOut

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.get("", response_model=list[RuleVersionOut])
async def list_rules(
    db: DbSession,
    user: CurrentUser,
    rule_family: Optional[str] = None,
    active_only: bool = False,
) -> list[RuleVersionOut]:
    q = select(RuleVersion)
    if rule_family:
        q = q.where(RuleVersion.rule_family == rule_family)
    if active_only:
        q = q.where(RuleVersion.is_active.is_(True))
    rows = (await db.execute(q.order_by(RuleVersion.rule_family, RuleVersion.version))).scalars().all()
    return [RuleVersionOut.model_validate(r) for r in rows]


@router.post("", response_model=RuleVersionOut, status_code=status.HTTP_201_CREATED)
async def create_rule(
    body: RuleVersionCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> RuleVersionOut:
    obj = RuleVersion(
        **body.model_dump(exclude_unset=True),
        created_by=user.id,
        activated_at=datetime.now(timezone.utc) if body.is_active else None,
    )
    db.add(obj)
    await db.flush()
    return RuleVersionOut.model_validate(obj)


@router.post("/{rule_id}/activate", response_model=RuleVersionOut)
async def activate_rule(
    rule_id: str,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> RuleVersionOut:
    obj = await db.get(RuleVersion, rule_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Rule version not found")
    # Deactivate peers in same family
    peers = (
        await db.execute(
            select(RuleVersion).where(
                RuleVersion.rule_family == obj.rule_family,
                RuleVersion.is_active.is_(True),
            )
        )
    ).scalars().all()
    for p in peers:
        p.is_active = False
    obj.is_active = True
    obj.activated_at = datetime.now(timezone.utc)
    await db.flush()
    return RuleVersionOut.model_validate(obj)
