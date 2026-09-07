"""Pydantic v2 schemas — analysis jobs and results."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class AnalyseRequest(BaseModel):
    event_id: str
    parameters: Optional[dict[str, Any]] = None
    force: bool = False


class AnalysisJobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    requested_by: Optional[str] = None
    status: str
    stage: str
    progress: float
    stages: Optional[list[Any]] = None
    current_message: Optional[str] = None
    error_message: Optional[str] = None
    celery_task_id: Optional[str] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    component_versions: Optional[dict[str, Any]] = None
    result_summary: Optional[dict[str, Any]] = None
    parameters: Optional[dict[str, Any]] = None
    created_at: datetime


class AnalyseResponse(BaseModel):
    job: AnalysisJobOut
    message: str = "Analysis queued"


class TimelineEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    sequence: int
    t_us: Optional[int] = None
    absolute_time: Optional[datetime] = None
    event_type: str
    source: Optional[str] = None
    label: Optional[str] = None
    description: Optional[str] = None
    confidence: Optional[float] = None
    evidence_ids: Optional[list[Any]] = None
    payload: Optional[dict[str, Any]] = None


class WaveformChannelOut(BaseModel):
    name: str
    channel_type: str
    phase: Optional[str] = None
    units: Optional[str] = None
    sample_count: Optional[int] = None
    samples: Optional[list[float]] = None
    timestamps_us: Optional[list[float]] = None


class WaveformMarkerOut(BaseModel):
    t_us: float
    label: str
    color: Optional[str] = None


class WaveformsResponse(BaseModel):
    event_id: str
    channels: list[WaveformChannelOut] = Field(default_factory=list)
    markers: list[WaveformMarkerOut] = Field(default_factory=list)
    note: Optional[str] = None


class ElectricalSummaryOut(BaseModel):
    event_id: str
    measurements: list[dict[str, Any]] = Field(default_factory=list)
    summary: Optional[dict[str, Any]] = None


class ProtectionSummaryOut(BaseModel):
    event_id: str
    operations: list[dict[str, Any]] = Field(default_factory=list)


class FaultClassificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    fault_type: str
    status: str
    involved_phases: Optional[list[Any]] = None
    ground_involved: Optional[bool] = None
    distance_km: Optional[float] = None
    location_method: Optional[str] = None
    impedance_ohm: Optional[float] = None
    impedance_angle_deg: Optional[float] = None
    duration_ms: Optional[float] = None
    inception_t_us: Optional[int] = None
    clearing_t_us: Optional[int] = None
    confidence: Optional[float] = None
    confidence_level: Optional[str] = None
    explanation: Optional[str] = None
    features: Optional[dict[str, Any]] = None
    is_primary: bool = True


class FaultLocationRowOut(BaseModel):
    algorithm: str
    status: str
    distance_km: Optional[float] = None
    distance_pct: Optional[float] = None
    unit: str = "km"
    notes: str = ""


class FaultCharacteristicsOut(BaseModel):
    event_id: str
    fault_type: str
    status: str
    confidence_level: Optional[str] = None
    involved_phases: Optional[list[Any]] = None
    ground_involved: Optional[bool] = None
    distance_km: Optional[float] = None
    location_method: Optional[str] = None
    inception_t_us: Optional[int] = None
    pickup_t_us: Optional[int] = None
    trip_t_us: Optional[int] = None
    clearing_t_us: Optional[int] = None
    currents: Optional[dict[str, Any]] = None
    sequences: Optional[dict[str, Any]] = None
    impedance: Optional[dict[str, Any]] = None
    location_algorithms: list[FaultLocationRowOut] = Field(default_factory=list)
    line_impedance_estimate: Optional[dict[str, Any]] = None
    limitations: list[str] = Field(default_factory=list)
    explanation: Optional[str] = None
