"""Pydantic v2 schemas — authentication."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


class UserBrief(BaseModel):
    """Minimal user payload returned with login tokens."""

    id: str
    username: str
    email: str
    full_name: Optional[str] = None
    role: str = "VIEWER"
    is_active: bool = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    username: str
    user_id: str
    user: Optional[UserBrief] = None


class UserBase(BaseModel):
    username: str
    email: str
    full_name: Optional[str] = None
    role: str = "VIEWER"
    is_active: bool = True


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=256)


class UserUpdate(BaseModel):
    email: Optional[str] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=256)


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: datetime
    last_login_at: Optional[datetime] = None
