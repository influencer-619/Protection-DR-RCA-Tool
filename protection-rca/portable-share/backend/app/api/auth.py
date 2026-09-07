"""Auth API — local login + optional OIDC."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.dependencies.auth import DbSession
from app.models import User
from app.schemas.auth import LoginRequest, TokenResponse
from app.services import auth_service, oidc_service
from app.services.audit_service import write_audit

router = APIRouter(prefix="/api/auth", tags=["auth"])


class AuthModeOut(BaseModel):
    mode: str
    oidc_enabled: bool
    oidc_authorize_url: Optional[str] = None


class OidcCallbackRequest(BaseModel):
    code: str
    redirect_uri: str
    state: Optional[str] = None


@router.get("/mode", response_model=AuthModeOut)
async def auth_mode(redirect_uri: Optional[str] = Query(None)) -> AuthModeOut:
    s = get_settings()
    enabled = oidc_service.oidc_enabled()
    url = None
    if enabled and redirect_uri:
        try:
            url = oidc_service.authorization_url(secrets.token_urlsafe(16), redirect_uri)
        except oidc_service.OidcError:
            url = None
    return AuthModeOut(
        mode=s.auth_mode or "local",
        oidc_enabled=enabled,
        oidc_authorize_url=url,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request, db: DbSession) -> TokenResponse:
    try:
        result = await auth_service.authenticate(
            db,
            body.username,
            body.password,
            ip_address=request.client.host if request.client else None,
            request_id=getattr(request.state, "request_id", None),
        )
    except auth_service.AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    return TokenResponse(**result)


@router.post("/oidc/callback", response_model=TokenResponse)
async def oidc_callback(
    body: OidcCallbackRequest, request: Request, db: DbSession
) -> TokenResponse:
    if not oidc_service.oidc_enabled():
        raise HTTPException(status_code=400, detail="OIDC auth mode is not enabled")
    try:
        tokens = oidc_service.exchange_code(body.code, body.redirect_uri)
        claims = oidc_service.validate_id_token(tokens["id_token"])
    except oidc_service.OidcError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    settings = get_settings()
    email = claims.get("email") or ""
    username = (
        claims.get("preferred_username")
        or claims.get("email")
        or claims.get("sub")
        or "oidc_user"
    )
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()
    if user is None and email:
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
    if user is None:
        user = User(
            username=str(username)[:128],
            email=email or f"{username}@oidc.local",
            full_name=claims.get("name"),
            hashed_password=hash_password(secrets.token_urlsafe(32)),
            role="VIEWER",
            is_active=True,
        )
        db.add(user)
        await db.flush()

    user.last_login_at = datetime.now(timezone.utc)
    token = create_access_token(
        subject=user.id, role=user.role, extra={"username": user.username}
    )
    await write_audit(
        db,
        action="LOGIN",
        user_id=user.id,
        object_type="User",
        object_id=user.id,
        ip_address=request.client.host if request.client else None,
        request_id=getattr(request.state, "request_id", None),
        new_value={"method": "oidc"},
    )
    await db.flush()
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=settings.access_token_expire_minutes * 60,
        role=user.role,
        username=user.username,
        user_id=user.id,
        user={
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "full_name": user.full_name,
            "role": user.role,
            "is_active": user.is_active,
        },
    )
