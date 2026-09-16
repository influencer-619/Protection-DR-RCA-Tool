"""Pydantic v2 schemas — plant hierarchy (Substation → VL → Bay → Feeder → IED)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class SubstationCreate(BaseModel):
    name: str
    code: Optional[str] = None
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


class VoltageLevelCreate(BaseModel):
    substation_id: str
    name: str
    code: Optional[str] = None
    nominal_voltage_kv: Optional[float] = None


class VoltageLevelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    substation_id: str
    code: str
    name: str
    nominal_voltage_kv: Optional[float] = None
    is_active: bool
    created_at: datetime


class BayCreate(BaseModel):
    voltage_level_id: str
    name: str
    code: Optional[str] = None
    bay_type: Optional[str] = None
    # Legacy optional fields
    substation_id: Optional[str] = None
    feeder_name: Optional[str] = None
    voltage_kv: Optional[float] = None


class BayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    substation_id: str
    voltage_level_id: Optional[str] = None
    code: str
    name: str
    feeder_name: Optional[str] = None
    voltage_kv: Optional[float] = None
    bay_type: Optional[str] = None
    is_active: bool
    created_at: datetime


class FeederCreate(BaseModel):
    bay_id: str
    name: str
    code: Optional[str] = None


class FeederOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    bay_id: str
    code: str
    name: str
    is_active: bool
    created_at: datetime


class RelayCreate(BaseModel):
    feeder_id: str
    name: str
    relay_tag: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    firmware_version: Optional[str] = None
    protection_functions: Optional[list[Any]] = None
    # Optional legacy
    substation_id: Optional[str] = None
    bay_id: Optional[str] = None


class RelayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    relay_tag: str
    name: str
    substation_id: Optional[str] = None
    bay_id: Optional[str] = None
    feeder_id: Optional[str] = None
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


# --- Nested plant tree ---


class PlantIedNode(BaseModel):
    id: str
    name: str
    relay_tag: str
    feeder_id: Optional[str] = None
    event_count: int = 0


class PlantFeederNode(BaseModel):
    id: str
    name: str
    code: str
    ieds: list[PlantIedNode] = Field(default_factory=list)


class PlantBayNode(BaseModel):
    id: str
    name: str
    code: str
    voltage_level_id: Optional[str] = None
    feeders: list[PlantFeederNode] = Field(default_factory=list)


class PlantVoltageLevelNode(BaseModel):
    id: str
    name: str
    code: str
    nominal_voltage_kv: Optional[float] = None
    bays: list[PlantBayNode] = Field(default_factory=list)


class PlantSubstationNode(BaseModel):
    id: str
    name: str
    code: str
    voltage_levels: list[PlantVoltageLevelNode] = Field(default_factory=list)


class PlantTreeOut(BaseModel):
    substations: list[PlantSubstationNode]


class IedContextOut(BaseModel):
    """Breadcrumb + IED details for the IED workspace."""

    ied: RelayOut
    feeder: FeederOut
    bay: BayOut
    voltage_level: Optional[VoltageLevelOut] = None
    substation: SubstationOut
    path_label: str


class MapEventToIedRequest(BaseModel):
    relay_id: str = Field(..., description="Target IED (relay) id")
