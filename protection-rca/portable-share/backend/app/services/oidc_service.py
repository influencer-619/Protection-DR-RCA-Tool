"""OIDC authentication helpers (optional when AUTH_MODE=oidc)."""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlencode

import httpx
from jose import jwt
from jose.exceptions import JWTError

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_jwks_cache: Optional[dict[str, Any]] = None


class OidcError(Exception):
    pass


def oidc_enabled() -> bool:
    s = get_settings()
    return (s.auth_mode or "local").lower() == "oidc" and bool(s.oidc_issuer)


def authorization_url(state: str, redirect_uri: str) -> str:
    s = get_settings()
    if not s.oidc_issuer or not s.oidc_client_id:
        raise OidcError("OIDC is not configured")
    base = s.oidc_issuer.rstrip("/") + "/protocol/openid-connect/auth"
    # Generic OIDC authorize path; Keycloak-style. Also try discovery.
    try:
        disc = _discovery()
        base = disc.get("authorization_endpoint") or base
    except Exception:  # noqa: BLE001
        pass
    params = {
        "client_id": s.oidc_client_id,
        "response_type": "code",
        "scope": "openid profile email",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{base}?{urlencode(params)}"


def _discovery() -> dict[str, Any]:
    s = get_settings()
    url = s.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration"
    with httpx.Client(timeout=10.0) as client:
        r = client.get(url)
        r.raise_for_status()
        return r.json()


def _jwks() -> dict[str, Any]:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    disc = _discovery()
    jwks_uri = disc["jwks_uri"]
    with httpx.Client(timeout=10.0) as client:
        r = client.get(jwks_uri)
        r.raise_for_status()
        _jwks_cache = r.json()
        return _jwks_cache


def exchange_code(code: str, redirect_uri: str) -> dict[str, Any]:
    s = get_settings()
    disc = _discovery()
    token_url = disc["token_endpoint"]
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": s.oidc_client_id,
        "client_secret": s.oidc_client_secret,
    }
    with httpx.Client(timeout=15.0) as client:
        r = client.post(token_url, data=data)
        if r.status_code >= 400:
            raise OidcError(f"Token exchange failed: {r.text}")
        return r.json()


def validate_id_token(id_token: str) -> dict[str, Any]:
    s = get_settings()
    jwks = _jwks()
    try:
        unverified = jwt.get_unverified_header(id_token)
        kid = unverified.get("kid")
        key = None
        for k in jwks.get("keys", []):
            if k.get("kid") == kid:
                key = k
                break
        if key is None and jwks.get("keys"):
            key = jwks["keys"][0]
        claims = jwt.decode(
            id_token,
            key,
            algorithms=[unverified.get("alg", "RS256")],
            audience=s.oidc_audience or s.oidc_client_id,
            issuer=s.oidc_issuer.rstrip("/"),
            options={"verify_at_hash": False},
        )
        return claims
    except JWTError as exc:
        raise OidcError(f"Invalid ID token: {exc}") from exc
