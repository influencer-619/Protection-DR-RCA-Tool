"""Pydantic v2 schemas — asset hierarchy."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SubstationCreate(BaseModel):
    code: str
    name: str
    region: Optional[str] = None
    voltage_levels_kv: Optional[list[Any]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    owner: Optional[str] = None
    metadata_json: Optional[dict[str, Any]] = None


class SubstationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    region: Optional[str] = None
    voltage_levels_kv: Optional[list[Any]] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    owner: Optional[str] = None
    is_active: bool
    created_at: datetime


class BayCreate(BaseModel):
    substation_id: str
    code: str
    name: str
    feeder_name: Optional[str] = None
    voltage_kv: Optional[float] = None
    bay_type: Optional[str] = None


class BayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    substation_id: str
    code: str
    name: str
    feeder_name: Optional[str] = None
    voltage_kv: Optional[float] = None
    bay_type: Optional[str] = None
    is_active: bool
    created_at: datetime


class RelayCreate(BaseModel):
    relay_tag: str
    name: str
    substation_id: Optional[str] = None
    bay_id: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    protection_functions: Optional[list[Any]] = None


class RelayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    relay_tag: str
    name: str
    substation_id: Optional[str] = None
    bay_id: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    protection_functions: Optional[list[Any]] = None
    is_active: bool
    created_at: datetime


class BreakerCreate(BaseModel):
    breaker_tag: str
    name: str
    substation_id: Optional[str] = None
    bay_id: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    rated_voltage_kv: Optional[float] = None
    expected_open_time_ms: Optional[float] = None


class BreakerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    breaker_tag: str
    name: str
    substation_id: Optional[str] = None
    bay_id: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    rated_voltage_kv: Optional[float] = None
    expected_open_time_ms: Optional[float] = None
    is_active: bool
    created_at: datetime


class AssetCreate(BaseModel):
    asset_tag: str
    name: str
    asset_type: str = Field(..., description="LINE|TRANSFORMER|BUS|CABLE|GENERATOR|...")
    substation_id: Optional[str] = None
    bay_id: Optional[str] = None
    nominal_voltage_kv: Optional[float] = None
    nominal_frequency_hz: Optional[float] = None
    parameters: Optional[dict[str, Any]] = None


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    asset_tag: str
    name: str
    asset_type: str
    substation_id: Optional[str] = None
    bay_id: Optional[str] = None
    nominal_voltage_kv: Optional[float] = None
    nominal_frequency_hz: Optional[float] = None
    is_active: bool
    created_at: datetime
