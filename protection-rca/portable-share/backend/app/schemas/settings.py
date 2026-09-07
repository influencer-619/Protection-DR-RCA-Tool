"""Pydantic v2 schemas — relay settings."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SettingCreate(BaseModel):
    relay_id: str
    parameter: str
    value: Optional[str] = None
    unit: Optional[str] = None
    enabled: bool = True
    setting_group: Optional[str] = None
    setting_group_id: Optional[str] = None
    setting_version_id: Optional[str] = None
    element: Optional[str] = None
    source: Optional[str] = None
    approval_status: str = "DRAFT"
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    notes: Optional[str] = None
    raw: Optional[dict[str, Any]] = None


class SettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    setting_id: str
    relay_id: str
    parameter: str
    value: Optional[str] = None
    unit: Optional[str] = None
    enabled: bool
    setting_group: Optional[str] = None
    element: Optional[str] = None
    version: int
    approval_status: str
    effective_from: Optional[datetime] = None
    effective_to: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime


class SettingListResponse(BaseModel):
    items: list[SettingOut]
    total: int


class SettingBulkCreate(BaseModel):
    relay_id: str
    settings: list[SettingCreate] = Field(default_factory=list)
    version_label: Optional[str] = None
