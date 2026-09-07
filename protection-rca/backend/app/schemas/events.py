"""Pydantic v2 schemas — events."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class EventCreate(BaseModel):
    event_id: Optional[str] = None
    substation_id: Optional[str] = None
    bay_id: Optional[str] = None
    asset_id: Optional[str] = None
    relay_id: Optional[str] = None
    breaker_id: Optional[str] = None
    feeder: Optional[str] = None
    event_datetime: Optional[datetime] = None
    nominal_voltage_kv: Optional[float] = None
    nominal_frequency_hz: Optional[float] = Field(default=50.0)
    description: Optional[str] = None
    tags: Optional[list[Any]] = None
    extra: Optional[dict[str, Any]] = None
    # Free-text plant labels when assets are not yet registered
    substation_name: Optional[str] = None
    bay_name: Optional[str] = None
    relay_tag: Optional[str] = None
    breaker_tag: Optional[str] = None
    asset_name: Optional[str] = None


class EventUpdate(BaseModel):
    feeder: Optional[str] = None
    event_datetime: Optional[datetime] = None
    nominal_voltage_kv: Optional[float] = None
    nominal_frequency_hz: Optional[float] = None
    description: Optional[str] = None
    status: Optional[str] = None
    tags: Optional[list[Any]] = None
    extra: Optional[dict[str, Any]] = None
    substation_id: Optional[str] = None
    bay_id: Optional[str] = None
    asset_id: Optional[str] = None
    relay_id: Optional[str] = None
    breaker_id: Optional[str] = None
    # Free-text plant labels (stored in event.extra)
    substation_name: Optional[str] = None
    bay_name: Optional[str] = None
    relay_tag: Optional[str] = None
    breaker_tag: Optional[str] = None
    asset_name: Optional[str] = None


class VerifyActiveSettingsRequest(BaseModel):
    """Engineer confirms the uploaded settings group was active at event time."""

    note: Optional[str] = Field(
        default=None,
        description="Optional note (how the active group was confirmed)",
    )
    confirmed: bool = Field(
        default=True,
        description="Must be true — engineer attestation that active group is correct",
    )


class ApproveSettingsFileRequest(BaseModel):
    """Engineer approves the uploaded settings package for this event."""

    note: Optional[str] = Field(
        default=None,
        description="Optional note (why / how the package was approved)",
    )
    confirmed: bool = Field(
        default=True,
        description="Must be true — engineer attestation that the file is approved",
    )
    also_verify_active_group: bool = Field(
        default=True,
        description="If true, also mark the active setting group as VERIFIED",
    )


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    substation_id: Optional[str] = None
    bay_id: Optional[str] = None
    asset_id: Optional[str] = None
    relay_id: Optional[str] = None
    breaker_id: Optional[str] = None
    engineer_id: Optional[str] = None
    feeder: Optional[str] = None
    event_datetime: Optional[datetime] = None
    nominal_voltage_kv: Optional[float] = None
    nominal_frequency_hz: Optional[float] = None
    description: Optional[str] = None
    status: str
    decision_state: Optional[str] = None
    data_quality: Optional[str] = None
    tags: Optional[list[Any]] = None
    extra: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    # Display labels from extra / plant_labels (not DB columns)
    substation_name: Optional[str] = None
    bay_name: Optional[str] = None
    relay_tag: Optional[str] = None
    breaker_tag: Optional[str] = None
    asset_name: Optional[str] = None
    fault_type: Optional[str] = None
    severity_summary: Optional[str] = None


class EventListResponse(BaseModel):
    items: list[EventOut]
    total: int
    page: int = 1
    page_size: int = 50
