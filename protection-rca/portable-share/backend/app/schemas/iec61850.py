"""Pydantic schemas — IEC 61850 (MMS) acquisition from an IED."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class Iec61850Connection(BaseModel):
    """Connection parameters; omitted fields fall back to the values saved on the IED."""

    host: Optional[str] = Field(None, description="IED IP address or hostname")
    port: Optional[int] = Field(None, ge=1, le=65535, description="MMS TCP port (default 102)")
    vendor_profile: Optional[str] = Field(None, description="AUTO, ABB, SIEMENS, GE, SCHNEIDER, SEL, …")
    remote_directory: Optional[str] = Field(
        None,
        description=(
            "Optional COMTRADE / disturbance path on the IED (same idea as ABB 800xA / Elipse). "
            "Leave empty to auto-walk /COMTRADE and the file store root."
        ),
    )
    connect_timeout_s: Optional[float] = Field(None, ge=1, le=120)
    request_timeout_s: Optional[float] = Field(None, ge=1, le=300)

    @field_validator("host")
    @classmethod
    def _host(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if any(ch in v for ch in " /\\?#@") or len(v) > 253:
            raise ValueError("host must be an IP address or hostname")
        return v

    @field_validator("remote_directory")
    @classmethod
    def _remote_dir(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        v = v.strip().replace("\\", "/")
        if not v:
            return None
        if len(v) > 256 or ".." in v or any(ch in v for ch in "*?<>|\0"):
            raise ValueError("remote_directory looks invalid")
        return v


class Iec61850FetchRequest(Iec61850Connection):
    records: list[str] = Field(default_factory=list, description="Record keys from /browse")
    include_settings: bool = True
    include_events: bool = True
    include_scl: bool = False
    description: Optional[str] = None


class Iec61850AutoFetchIn(Iec61850Connection):
    enabled: bool
    interval_min: int = Field(5, description="Minutes between checks")
    include_settings: bool = True
    include_events: bool = True
    auto_analyse: bool = True
    import_existing: bool = Field(
        False, description="On enable, also ingest records already on the IED (default: only new ones)"
    )


class Iec61850AutoFetchOut(BaseModel):
    enabled: bool = False
    interval_min: int = 5
    include_settings: bool = True
    include_events: bool = True
    auto_analyse: bool = True
    import_existing: bool = False
    last_run_at: Optional[str] = None
    next_run_at: Optional[str] = None
    last_status: Optional[str] = None
    last_error: Optional[str] = None
    last_new_records: Optional[int] = None
    last_event_at: Optional[str] = None
    records_on_ied: Optional[int] = None
    total_events_created: int = 0
    baseline_done: bool = False
    scheduler_running: bool = False
    interval_choices: list[int] = Field(default_factory=list)


class VendorProfileOut(BaseModel):
    id: str
    label: str
    families: str
    notes: str = ""
    comtrade_dirs: list[str] = Field(default_factory=list)


class Iec61850InfoOut(BaseModel):
    library: dict[str, Any]
    vendors: list[VendorProfileOut]


class Iec61850ConnectionOut(BaseModel):
    host: Optional[str] = None
    port: int = 102
    vendor_profile: str = "AUTO"
    remote_directory: Optional[str] = None
    connect_timeout_s: float = 10.0
    request_timeout_s: float = 20.0
    last_nameplate: Optional[dict[str, Any]] = None
    last_seen_at: Optional[str] = None


class FetchedEventOut(BaseModel):
    id: str
    event_id: str
    record: Optional[str] = None
    files: list[str]
    package_ready: bool


class Iec61850FetchOut(BaseModel):
    events: list[FetchedEventOut]
    warnings: list[str] = Field(default_factory=list)
    nameplate: dict[str, Any] = Field(default_factory=dict)
    profile: Optional[str] = None
