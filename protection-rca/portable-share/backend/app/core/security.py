"""Security helpers: password hashing, JWT, RBAC."""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

import bcrypt
from jose import JWTError, jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


class Role(str, Enum):
    VIEWER = "VIEWER"
    ANALYST = "ANALYST"
    PROTECTION_ENGINEER = "PROTECTION_ENGINEER"
    APPROVER = "APPROVER"
    ADMIN = "ADMIN"


ROLE_HIERARCHY = {
    Role.VIEWER: 1,
    Role.ANALYST: 2,
    Role.PROTECTION_ENGINEER: 3,
    Role.APPROVER: 4,
    Role.ADMIN: 5,
}


def _to_bytes(value: str) -> bytes:
    return value.encode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bytes(plain), _to_bytes(hashed))
    except (ValueError, TypeError):
        return False


def hash_password(password: str) -> str:
    raw = _to_bytes(password)
    if len(raw) > 72:
        raise ValueError("Password cannot exceed 72 bytes")
    return bcrypt.hashpw(raw, bcrypt.gensalt()).decode("utf-8")


def create_access_token(subject: str, role: str, extra: Optional[dict] = None) -> str:
    settings = get_settings()
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload: dict[str, Any] = {"sub": subject, "role": role, "exp": expire}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    return jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])


def role_at_least(user_role: str, required: Role) -> bool:
    try:
        return ROLE_HIERARCHY[Role(user_role)] >= ROLE_HIERARCHY[required]
    except (ValueError, KeyError):
        return False


class TokenError(Exception):
    pass


def safe_decode(token: str) -> dict[str, Any]:
    try:
        return decode_access_token(token)
    except JWTError as exc:
        raise TokenError("Invalid or expired token") from exc
