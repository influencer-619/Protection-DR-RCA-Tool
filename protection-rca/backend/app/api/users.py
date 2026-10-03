"""User management API (auth database)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from app.core.security import Role, hash_password
from app.dependencies.auth import AuthDbSession, CurrentUser, DbSession, require_role
from app.models import User
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.services.audit_service import write_audit

router = APIRouter(prefix="/api/users", tags=["users"])

_VALID_ROLES = {r.value for r in Role}


def _validate_role(role: str | None) -> str | None:
    if role is None:
        return None
    text = str(role).strip().upper()
    if text not in _VALID_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Allowed: {', '.join(sorted(_VALID_ROLES))}",
        )
    return text


async def _active_admin_count(auth_db: AuthDbSession) -> int:
    result = await auth_db.execute(
        select(func.count())
        .select_from(User)
        .where(User.role == Role.ADMIN.value, User.is_active.is_(True))
    )
    return int(result.scalar_one() or 0)


async def _ensure_unique(
    auth_db: AuthDbSession,
    *,
    username: str | None,
    email: str | None,
    exclude_id: str | None = None,
) -> None:
    if username:
        q = select(User).where(User.username == username)
        if exclude_id:
            q = q.where(User.id != exclude_id)
        if (await auth_db.execute(q)).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Username already exists")
    if email:
        q = select(User).where(User.email == email)
        if exclude_id:
            q = q.where(User.id != exclude_id)
        if (await auth_db.execute(q)).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="Email already exists")


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
    role = _validate_role(body.role) or Role.VIEWER.value
    await _ensure_unique(auth_db, username=body.username, email=body.email)
    obj = User(
        username=body.username.strip(),
        email=body.email.strip(),
        full_name=(body.full_name or "").strip() or None,
        role=role,
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
        new_value={"username": obj.username, "role": obj.role, "is_active": obj.is_active},
    )
    return UserOut.model_validate(obj)


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: str,
    body: UserUpdate,
    auth_db: AuthDbSession,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> UserOut:
    obj = await auth_db.get(User, user_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="User not found")

    data = body.model_dump(exclude_unset=True)
    password = data.pop("password", None)
    if "role" in data:
        data["role"] = _validate_role(data["role"])
    if "username" in data and data["username"] is not None:
        data["username"] = str(data["username"]).strip()
    if "email" in data and data["email"] is not None:
        data["email"] = str(data["email"]).strip()
    if "full_name" in data and data["full_name"] is not None:
        data["full_name"] = str(data["full_name"]).strip() or None

    await _ensure_unique(
        auth_db,
        username=data.get("username"),
        email=data.get("email"),
        exclude_id=obj.id,
    )

    becoming_inactive = data.get("is_active") is False and obj.is_active
    demoting_admin = (
        obj.role == Role.ADMIN.value
        and data.get("role") is not None
        and data.get("role") != Role.ADMIN.value
    )
    if (becoming_inactive or demoting_admin) and obj.role == Role.ADMIN.value:
        if await _active_admin_count(auth_db) <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot deactivate or demote the last active administrator",
            )

    old = {
        "username": obj.username,
        "email": obj.email,
        "full_name": obj.full_name,
        "role": obj.role,
        "is_active": obj.is_active,
    }
    for k, v in data.items():
        setattr(obj, k, v)
    if password:
        obj.hashed_password = hash_password(password)
    await auth_db.flush()
    await write_audit(
        db,
        action="UPDATE",
        user_id=user.id,
        object_type="User",
        object_id=obj.id,
        old_value=old,
        new_value={
            "username": obj.username,
            "email": obj.email,
            "full_name": obj.full_name,
            "role": obj.role,
            "is_active": obj.is_active,
            "password_changed": bool(password),
        },
    )
    return UserOut.model_validate(obj)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: str,
    auth_db: AuthDbSession,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> None:
    obj = await auth_db.get(User, user_id)
    if obj is None:
        raise HTTPException(status_code=404, detail="User not found")
    if obj.id == user.id:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    if obj.role == Role.ADMIN.value and obj.is_active:
        if await _active_admin_count(auth_db) <= 1:
            raise HTTPException(
                status_code=400,
                detail="Cannot delete the last active administrator",
            )
    await write_audit(
        db,
        action="DELETE",
        user_id=user.id,
        object_type="User",
        object_id=obj.id,
        old_value={"username": obj.username, "role": obj.role, "email": obj.email},
    )
    await auth_db.delete(obj)
    await auth_db.flush()
