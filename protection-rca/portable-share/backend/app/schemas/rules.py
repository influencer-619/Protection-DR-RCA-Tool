"""Pydantic v2 schemas — rule / model versions, audit, dashboard, comtrade."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class RuleVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    rule_family: str
    version: str
    name: str
    description: Optional[str] = None
    is_active: bool
    checksum_sha256: Optional[str] = None
    activated_at: Optional[datetime] = None
    created_at: datetime


class RuleVersionCreate(BaseModel):
    rule_family: str
    version: str
    name: str
    description: Optional[str] = None
    rules_payload: Optional[dict[str, Any]] = None
    is_active: bool = False


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    model_name: str
    version: str
    model_type: Optional[str] = None
    description: Optional[str] = None
    is_active: bool
    framework: Optional[str] = None
    metrics: Optional[dict[str, Any]] = None
    activated_at: Optional[datetime] = None
    created_at: datetime


class ModelVersionCreate(BaseModel):
    model_name: str
    version: str
    model_type: Optional[str] = None
    description: Optional[str] = None
    framework: Optional[str] = None
    metrics: Optional[dict[str, Any]] = None
    hyperparameters: Optional[dict[str, Any]] = None
    is_active: bool = False


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: Optional[str] = None
    timestamp: datetime
    action: str
    object_type: Optional[str] = None
    object_id: Optional[str] = None
    ip_address: Optional[str] = None
    request_id: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None


class AuditListResponse(BaseModel):
    items: list[AuditLogOut]
    total: int


class DashboardTrendPoint(BaseModel):
    date: str
    events: int = 0
    analysed: int = 0
    review: int = 0
    issues: int = 0


class DashboardDqBreakdown(BaseModel):
    good: int = 0
    acceptable: int = 0
    warning: int = 0
    poor: int = 0
    invalid: int = 0
    unknown: int = 0
    not_validated: int = 0
    unsupported: int = 0


class DashboardAttentionItem(BaseModel):
    id: str
    event_id: str
    reason: str
    severity: str = "MEDIUM"
    href_status: str = ""


class DashboardRecentEvent(BaseModel):
    id: str
    event_id: str
    event_datetime: Optional[str] = None
    location: str = "—"
    relay: str = "—"
    fault_type: Optional[str] = None
    protection_summary: str = "—"
    consistency_summary: str = "—"
    rca_status: str = "—"
    severity: Optional[str] = None
    status: str = ""
    data_quality: Optional[str] = None


class DashboardStats(BaseModel):
    total_events: int = 0
    awaiting_analysis: int = 0
    awaiting_review: int = 0
    completed_reports: int = 0
    consistency_issues: int = 0
    high_severity_findings: int = 0
    rca_inconclusive: int = 0
    parser_dq_issues: int = 0
    trend_30d: list[DashboardTrendPoint] = Field(default_factory=list)
    data_quality: DashboardDqBreakdown = Field(default_factory=DashboardDqBreakdown)
    attention: list[DashboardAttentionItem] = Field(default_factory=list)
    recent_events: list[DashboardRecentEvent] = Field(default_factory=list)


class ComtradeDetectRequest(BaseModel):
    filenames: list[str] = Field(default_factory=list)
    # When uploading bytes via multipart, body may be empty


class ComtradeDetectResponse(BaseModel):
    is_comtrade: bool
    status: str
    revision_year: Optional[int] = None
    data_format: Optional[str] = None
    container: Optional[str] = None
    encoding: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    warnings: list[str] = Field(default_factory=list)


class ComtradeValidateResponse(BaseModel):
    status: str
    data_quality: Optional[str] = None
    issues: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    details: Optional[dict[str, Any]] = None


class ComtradeParseResponse(BaseModel):
    success: bool
    record_id: Optional[str] = None
    station: Optional[str] = None
    device: Optional[str] = None
    samples: Optional[int] = None
    analog_channels: Optional[int] = None
    digital_channels: Optional[int] = None
    sample_rate_hz: Optional[float] = None
    detection: Optional[dict[str, Any]] = None
    validation: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    stages: list[str] = Field(default_factory=list)
