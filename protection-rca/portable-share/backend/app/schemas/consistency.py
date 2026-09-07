"""Pydantic v2 schemas — consistency findings."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ConsistencyFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    finding_id: str
    event_id: str
    element: str
    check_type: str
    setting_source: Optional[str] = None
    setting_version: Optional[str] = None
    expected: Optional[dict[str, Any]] = None
    observed: Optional[dict[str, Any]] = None
    status: str
    severity: str
    evidence_ids: Optional[list[Any]] = None
    explanation: Optional[str] = None
    confidence: Optional[float] = None
    rule_version: Optional[str] = None
    created_at: datetime


class ConsistencyListResponse(BaseModel):
    event_id: str
    findings: list[ConsistencyFindingOut]
    summary: Optional[dict[str, Any]] = None
    overall_status: str = "NOT_AVAILABLE"
    setting_source: Optional[dict[str, Any]] = None
