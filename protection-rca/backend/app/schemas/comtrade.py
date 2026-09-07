"""COMTRADE API schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.rules import (
    ComtradeDetectRequest,
    ComtradeDetectResponse,
    ComtradeParseResponse,
    ComtradeValidateResponse,
)


class ComtradeFileOut(BaseModel):
    """Parsed COMTRADE metadata for an event (populated after analysis ingest)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    station_name: Optional[str] = None
    recording_device: Optional[str] = None
    revision_year: Optional[int] = None
    start_timestamp: Optional[datetime] = None
    trigger_timestamp: Optional[datetime] = None
    sample_rate_hz: Optional[float] = None
    total_samples: Optional[int] = None
    analog_channel_count: Optional[int] = None
    digital_channel_count: Optional[int] = None
    frequency_hz: Optional[float] = None
    line_frequency_hz: Optional[float] = None
    validation_status: Optional[str] = None
    data_quality: Optional[str] = None
    parse_warnings: Optional[list[Any]] = None
    format_detected: Optional[str] = Field(
        default=None, description="From header_metadata.data_format"
    )
    support_status: Optional[str] = Field(
        default=None, description="Detection/support status when available"
    )
    header_metadata: Optional[dict[str, Any]] = None


__all__ = [
    "ComtradeDetectRequest",
    "ComtradeDetectResponse",
    "ComtradeParseResponse",
    "ComtradeValidateResponse",
    "ComtradeFileOut",
]
