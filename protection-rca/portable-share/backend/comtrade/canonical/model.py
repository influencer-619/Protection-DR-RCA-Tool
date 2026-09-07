"""Canonical disturbance record schema for COMTRADE ingest."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class AnalogChannel:
    """Analog channel definition from a COMTRADE CFG."""

    index: int
    name: str
    phase: str = ""
    ccbm: str = ""
    unit: str = ""
    a: float = 1.0
    b: float = 0.0
    skew: float = 0.0
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    primary: Optional[float] = None
    secondary: Optional[float] = None
    ps: str = "P"  # P=primary, S=secondary


@dataclass
class DigitalChannel:
    """Status / digital channel definition from a COMTRADE CFG."""

    index: int
    name: str
    phase: str = ""
    ccbm: str = ""
    normal_state: int = 0  # y field: normal state 0 or 1


@dataclass
class SampleRateSection:
    """One sample-rate / endsamp pair from the CFG nrates block."""

    sample_rate_hz: float
    end_sample: int


@dataclass
class CanonicalDisturbanceRecord:
    """Normalized COMTRADE disturbance record used by the RCA pipeline.

    Unsupported or unavailable fields are left empty / None and surfaced via
    ``quality`` — this model never invents missing values.
    """

    record_id: str
    standard: str  # IEEE | IEC
    revision: str  # 1991 | 1999 | 2001 | 2013
    container: str  # CFG_DAT | CFF
    station: str = ""
    device: str = ""
    nominal_frequency: float = 50.0
    start_time: Optional[datetime] = None
    trigger_time: Optional[datetime] = None
    sample_rates: list[SampleRateSection] = field(default_factory=list)
    analog_channels: list[AnalogChannel] = field(default_factory=list)
    digital_channels: list[DigitalChannel] = field(default_factory=list)
    samples: int = 0
    timestamps: list[int] = field(default_factory=list)  # µs from start (normalized)
    raw_values: dict[str, list[float]] = field(default_factory=dict)
    scaled_values: dict[str, list[float]] = field(default_factory=dict)
    units: dict[str, str] = field(default_factory=dict)
    channel_metadata: dict[str, Any] = field(default_factory=dict)
    quality: dict[str, Any] = field(default_factory=dict)
    source_files: list[str] = field(default_factory=list)
    parser_version: str = "1.0.0"
    data_format: str = "ASCII"  # ASCII | BINARY | BINARY32 | FLOAT32
    time_multiplier: float = 1.0
    time_code: Optional[str] = None
    local_code: Optional[str] = None
    tmq_code: Optional[str] = None
    leapsec: Optional[str] = None
    unsupported_features: list[str] = field(default_factory=list)
