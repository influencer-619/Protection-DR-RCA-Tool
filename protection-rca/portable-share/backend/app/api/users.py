"""User management API (auth database)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.core.security import Role, hash_password
from app.dependencies.auth import AuthDbSession, CurrentUser, DbSession, require_role
from app.models import User
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.services.audit_service import write_audit

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return UserOut.model_validate(user)


@router.get("", response_model=list[UserOut])
async def list_users(
    auth_db: AuthDbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> list[UserOut]:
    rows = (await auth_db.execute(select(User).order_by(User.username))).scalars().all()
    return [UserOut.model_validate(r) for r in rows]


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    auth_db: AuthDbSession,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> UserOut:
    existing = await auth_db.execute(
        select(User).where(
            (User.username == body.username) | (User.email == body.email)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username or email already exists")
    obj = User(
        username=body.username,
        email=body.email,
        full_name=body.full_name,
        role=body.role,
        is_active=body.is_active,
        hashed_password=hash_password(body.password),
    )
    auth_db.add(obj)
    await auth_db.flush()
    await write_audit(
        db,
        action="CREATE",
        user_id=user.id,
        object_type="User",
        object_id=obj.id,
        new_value={"username": obj.username, "role": obj.role},
    )
    return UserOut.model_validate(obj)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdate,
    auth_db: AuthDbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> UserOut:
    obj = await auth_db.get(User, user_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="User not found")
    data = body.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    for k, v in data.items():
        setattr(obj, k, v)
    if password:
        obj.hashed_password = hash_password(password)
    await auth_db.flush()
    return UserOut.model_validate(obj)
