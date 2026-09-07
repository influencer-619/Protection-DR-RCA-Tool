"""Pydantic v2 schemas — reports."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReportCreate(BaseModel):
    event_id: str
    report_type: str = "RCA"
    title: Optional[str] = None
    format: str = "JSON"


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    report_type: str
    title: str
    status: str
    template_version: Optional[str] = None
    storage_key: Optional[str] = None
    format: Optional[str] = None
    summary: Optional[str] = None
    sections: Optional[dict[str, Any]] = None
    generated_by: Optional[str] = None
    generated_at: Optional[datetime] = None
    created_at: datetime


class ReportListResponse(BaseModel):
    items: list[ReportOut] = Field(default_factory=list)
    total: int = 0
