"""Model version registry API (statistical/ML artefacts — no generative AI)."""

from __future__ import annotations

from typing import Annotated

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import ModelVersion
from app.schemas.models import ModelVersionCreate, ModelVersionOut

router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("", response_model=list[ModelVersionOut])
async def list_models(
    db: DbSession,
    user: CurrentUser,
    model_name: Optional[str] = None,
    active_only: bool = False,
) -> list[ModelVersionOut]:
    q = select(ModelVersion)
    if model_name:
        q = q.where(ModelVersion.model_name == model_name)
    if active_only:
        q = q.where(ModelVersion.is_active.is_(True))
    rows = (
        await db.execute(q.order_by(ModelVersion.model_name, ModelVersion.version))
    ).scalars().all()
    return [ModelVersionOut.model_validate(r) for r in rows]


@router.post("", response_model=ModelVersionOut, status_code=status.HTTP_201_CREATED)
async def create_model(
    body: ModelVersionCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> ModelVersionOut:
    obj = ModelVersion(
        **body.model_dump(exclude_unset=True),
        created_by=user.id,
        activated_at=datetime.now(timezone.utc) if body.is_active else None,
    )
    db.add(obj)
    await db.flush()
    return ModelVersionOut.model_validate(obj)


@router.post("/{model_id}/activate", response_model=ModelVersionOut)
async def activate_model(
    model_id: str,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> ModelVersionOut:
    obj = await db.get(ModelVersion, model_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Model version not found")
    peers = (
        await db.execute(
            select(ModelVersion).where(
                ModelVersion.model_name == obj.model_name,
                ModelVersion.is_active.is_(True),
            )
        )
    ).scalars().all()
    for p in peers:
        p.is_active = False
    obj.is_active = True
    obj.activated_at = datetime.now(timezone.utc)
    await db.flush()
    return ModelVersionOut.model_validate(obj)
