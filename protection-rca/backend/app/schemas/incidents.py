"""Pydantic schemas — parent Incident correlation."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class IncidentCreate(BaseModel):
    mode: str = Field(default="MANUAL", description="CASCADE_LBB | LINE_MULTI_END | MANUAL")
    correlation_reason: str = Field(
        ...,
        description="Explicit reason — never TIMESTAMP_ONLY",
    )
    correlation_detail: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    event_ids: list[str] = Field(
        default_factory=list,
        description="Optional initial event ids to link as SOURCE",
    )


class IncidentLinkRequest(BaseModel):
    event_id: str
    role: str = "SOURCE"
    link_reason: str = Field(
        default="ENGINEER_LINK",
        description="Must be an allowed explicit reason (not timestamp-only)",
    )
    link_detail: Optional[str] = None


class IncidentUnlinkRequest(BaseModel):
    event_id: str
    detail: Optional[str] = None


class IncidentLateAttachRequest(BaseModel):
    event_id: str
    role: str = "LATE_ATTACH"
    detail: Optional[str] = None


class IncidentMemberOut(BaseModel):
    member_id: str
    event_id: str
    event_code: Optional[str] = None
    role: str
    link_reason: str
    link_detail: Optional[str] = None
    linked_by: Optional[str] = None
    active: bool = True


class IncidentOut(BaseModel):
    id: str
    incident_code: str
    title: Optional[str] = None
    description: Optional[str] = None
    mode: str
    status: str
    correlation_reason: str
    correlation_detail: Optional[str] = None
    combined_event_id: Optional[str] = None
    created_by: Optional[str] = None
    created_at: Optional[str] = None
    members: list[IncidentMemberOut] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)
