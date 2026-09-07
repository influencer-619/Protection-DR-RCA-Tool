"""Authentication service — local JWT login against seeded users."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.models import User
from app.services.audit_service import write_audit


class AuthError(Exception):
    pass


async def authenticate(
    db: AsyncSession,
    username: str,
    password: str,
    *,
    ip_address: Optional[str] = None,
    request_id: Optional[str] = None,
) -> dict:
    result = await db.execute(
        select(User).where(
            (User.username == username) | (User.email == username)
        )
    )
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise AuthError("Invalid username or password")
    if not verify_password(password, user.hashed_password):
        raise AuthError("Invalid username or password")

    settings = get_settings()
    token = create_access_token(subject=user.id, role=user.role, extra={"username": user.username})
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()
    await write_audit(
        db,
        action="LOGIN",
        user_id=user.id,
        object_type="User",
        object_id=user.id,
        ip_address=ip_address,
        request_id=request_id,
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
        "role": user.role,
        "username": user.username,
        "user_id": user.id,
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
            "created_at": user.created_at,
            "last_login_at": user.last_login_at,
        },
    }
