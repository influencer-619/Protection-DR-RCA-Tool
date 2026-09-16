"""
SQLAlchemy 2.0 ORM models for the Protection Disturbance Record / COMTRADE RCA platform.

All mapped classes are exported from this package. Import Base from app.database.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from app.database import AuthBase, Base
from app.models.base_mixins import TimestampMixin, UUIDPrimaryKeyMixin, generate_uuid


# ---------------------------------------------------------------------------
# Identity & access (AUTH database — separate from plant/events DB)
# ---------------------------------------------------------------------------


class User(AuthBase, UUIDPrimaryKeyMixin, TimestampMixin):
    """Platform user account (stored in auth DB only)."""

    __tablename__ = "users"
    __table_args__ = (
        Index("ix_users_email", "email", unique=True),
        Index("ix_users_username", "username", unique=True),
    )

    username: Mapped[str] = mapped_column(String(128), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Any] = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # Role stored as enum string (VIEWER, ANALYST, PROTECTION_ENGINEER, APPROVER, ADMIN)
    role: Mapped[str] = mapped_column(String(64), nullable=False, default="VIEWER")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_login_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    preferences: Mapped[Any] = mapped_column(JSON, nullable=True)


class Role(AuthBase, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Optional role catalog table for RBAC extension.

    Day-to-day authorization uses User.role (string enum). This table supports
    custom role definitions and metadata without replacing the enum values.
    """

    __tablename__ = "roles"
    __table_args__ = (Index("ix_roles_code", "code", unique=True),)

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Any] = mapped_column(Text, nullable=True)
    permissions: Mapped[Any] = mapped_column(JSON, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


# ---------------------------------------------------------------------------
# Asset hierarchy: Substation → VoltageLevel → Bay → Feeder → IED (Relay)
# ---------------------------------------------------------------------------


class Substation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Electrical substation (site)."""

    __tablename__ = "substations"
    __table_args__ = (
        Index("ix_substations_code", "code", unique=True),
        Index("ix_substations_name", "name"),
    )

    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[Any] = mapped_column(String(128), nullable=True)
    voltage_levels_kv: Mapped[Any] = mapped_column(JSON, nullable=True)
    latitude: Mapped[Any] = mapped_column(Float, nullable=True)
    longitude: Mapped[Any] = mapped_column(Float, nullable=True)
    owner: Mapped[Any] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[Any] = mapped_column(
        "metadata", JSON, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    voltage_levels: Mapped[list[VoltageLevel]] = relationship(
        "VoltageLevel", back_populates="substation", cascade="all, delete-orphan"
    )
    bays: Mapped[list[Bay]] = relationship(
        "Bay", back_populates="substation", cascade="all, delete-orphan"
    )
    assets: Mapped[list[Asset]] = relationship("Asset", back_populates="substation")
    relays: Mapped[list[Relay]] = relationship("Relay", back_populates="substation")
    breakers: Mapped[list[Breaker]] = relationship(
        "Breaker", back_populates="substation"
    )
    events: Mapped[list[Event]] = relationship("Event", back_populates="substation")


class VoltageLevel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Voltage level under a substation (e.g. 132 kV, 33 kV)."""

    __tablename__ = "voltage_levels"
    __table_args__ = (
        UniqueConstraint(
            "substation_id", "code", name="uq_voltage_levels_substation_code"
        ),
        Index("ix_voltage_levels_substation_id", "substation_id"),
    )

    substation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("substations.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    nominal_voltage_kv: Mapped[Any] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Any] = mapped_column("metadata", JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    substation: Mapped[Substation] = relationship(
        "Substation", back_populates="voltage_levels"
    )
    bays: Mapped[list[Bay]] = relationship(
        "Bay", back_populates="voltage_level"
    )


class Bay(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Bay under a voltage level (named by user, e.g. 'line1 bay')."""

    __tablename__ = "bays"
    __table_args__ = (
        UniqueConstraint("substation_id", "code", name="uq_bays_substation_code"),
        Index("ix_bays_substation_id", "substation_id"),
        Index("ix_bays_voltage_level_id", "voltage_level_id"),
        Index("ix_bays_feeder_name", "feeder_name"),
    )

    substation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("substations.id", ondelete="CASCADE"), nullable=False
    )
    voltage_level_id: Mapped[Any] = mapped_column(
        String(36),
        ForeignKey("voltage_levels.id", ondelete="CASCADE"),
        nullable=True,
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    feeder_name: Mapped[Any] = mapped_column(String(255), nullable=True)
    voltage_kv: Mapped[Any] = mapped_column(Float, nullable=True)
    bay_type: Mapped[Any] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[Any] = mapped_column(
        "metadata", JSON, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    substation: Mapped[Substation] = relationship("Substation", back_populates="bays")
    voltage_level: Mapped[Any] = relationship("VoltageLevel", back_populates="bays")
    feeders: Mapped[list[Feeder]] = relationship(
        "Feeder", back_populates="bay", cascade="all, delete-orphan"
    )
    assets: Mapped[list[Asset]] = relationship("Asset", back_populates="bay")
    relays: Mapped[list[Relay]] = relationship("Relay", back_populates="bay")
    breakers: Mapped[list[Breaker]] = relationship("Breaker", back_populates="bay")
    events: Mapped[list[Event]] = relationship("Event", back_populates="bay")


class Feeder(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Feeder under a bay."""

    __tablename__ = "feeders"
    __table_args__ = (
        UniqueConstraint("bay_id", "code", name="uq_feeders_bay_code"),
        Index("ix_feeders_bay_id", "bay_id"),
    )

    bay_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("bays.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    metadata_json: Mapped[Any] = mapped_column("metadata", JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    bay: Mapped[Bay] = relationship("Bay", back_populates="feeders")
    ieds: Mapped[list[Relay]] = relationship("Relay", back_populates="feeder")


class Asset(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Protected primary equipment (line, transformer, bus, cable, etc.)."""

    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("substation_id", "asset_tag", name="uq_assets_sub_tag"),
        Index("ix_assets_substation_id", "substation_id"),
        Index("ix_assets_bay_id", "bay_id"),
        Index("ix_assets_asset_type", "asset_type"),
    )

    substation_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("substations.id", ondelete="SET NULL"), nullable=True
    )
    bay_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("bays.id", ondelete="SET NULL"), nullable=True
    )
    asset_tag: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    asset_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # LINE, TRANSFORMER, BUS, CABLE, GENERATOR, ...
    nominal_voltage_kv: Mapped[Any] = mapped_column(Float, nullable=True)
    nominal_frequency_hz: Mapped[Any] = mapped_column(Float, nullable=True)
    manufacturer: Mapped[Any] = mapped_column(String(128), nullable=True)
    model: Mapped[Any] = mapped_column(String(128), nullable=True)
    parameters: Mapped[Any] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    substation: Mapped[Any] = relationship(
        "Substation", back_populates="assets"
    )
    bay: Mapped[Any] = relationship("Bay", back_populates="assets")
    events: Mapped[list[Event]] = relationship("Event", back_populates="asset")


class Relay(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Protection relay / IED (upload and analysis locus)."""

    __tablename__ = "relays"
    __table_args__ = (
        UniqueConstraint("substation_id", "relay_tag", name="uq_relays_sub_tag"),
        Index("ix_relays_bay_id", "bay_id"),
        Index("ix_relays_feeder_id", "feeder_id"),
        Index("ix_relays_manufacturer_model", "manufacturer", "model"),
    )

    substation_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("substations.id", ondelete="SET NULL"), nullable=True
    )
    bay_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("bays.id", ondelete="SET NULL"), nullable=True
    )
    feeder_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("feeders.id", ondelete="CASCADE"), nullable=True
    )
    relay_tag: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    manufacturer: Mapped[Any] = mapped_column(String(128), nullable=True)
    model: Mapped[Any] = mapped_column(String(128), nullable=True)
    firmware_version: Mapped[Any] = mapped_column(String(64), nullable=True)
    serial_number: Mapped[Any] = mapped_column(String(128), nullable=True)
    protection_functions: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )  # e.g. ["21", "50/51", "67N", "87L"]
    ip_address: Mapped[Any] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[Any] = mapped_column(
        "metadata", JSON, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    substation: Mapped[Any] = relationship(
        "Substation", back_populates="relays"
    )
    bay: Mapped[Any] = relationship("Bay", back_populates="relays")
    feeder: Mapped[Any] = relationship("Feeder", back_populates="ieds")
    settings: Mapped[list[Setting]] = relationship(
        "Setting", back_populates="relay", cascade="all, delete-orphan"
    )
    setting_groups: Mapped[list[SettingGroup]] = relationship(
        "SettingGroup", back_populates="relay", cascade="all, delete-orphan"
    )
    setting_versions: Mapped[list[SettingVersion]] = relationship(
        "SettingVersion", back_populates="relay", cascade="all, delete-orphan"
    )
    events: Mapped[list[Event]] = relationship("Event", back_populates="relay")
    protection_operations: Mapped[list[ProtectionOperation]] = relationship(
        "ProtectionOperation", back_populates="relay"
    )

class Breaker(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Circuit breaker associated with a bay / protected asset."""

    __tablename__ = "breakers"
    __table_args__ = (
        UniqueConstraint("substation_id", "breaker_tag", name="uq_breakers_sub_tag"),
        Index("ix_breakers_bay_id", "bay_id"),
    )

    substation_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("substations.id", ondelete="SET NULL"), nullable=True
    )
    bay_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("bays.id", ondelete="SET NULL"), nullable=True
    )
    breaker_tag: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    manufacturer: Mapped[Any] = mapped_column(String(128), nullable=True)
    model: Mapped[Any] = mapped_column(String(128), nullable=True)
    rated_voltage_kv: Mapped[Any] = mapped_column(Float, nullable=True)
    rated_current_a: Mapped[Any] = mapped_column(Float, nullable=True)
    interrupting_capacity_ka: Mapped[Any] = mapped_column(
        Float, nullable=True
    )
    expected_open_time_ms: Mapped[Any] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[Any] = mapped_column(
        "metadata", JSON, nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    substation: Mapped[Any] = relationship(
        "Substation", back_populates="breakers"
    )
    bay: Mapped[Any] = relationship("Bay", back_populates="breakers")
    events: Mapped[list[Event]] = relationship("Event", back_populates="breaker")
    protection_operations: Mapped[list[ProtectionOperation]] = relationship(
        "ProtectionOperation", back_populates="breaker"
    )


# ---------------------------------------------------------------------------
# Relay settings
# ---------------------------------------------------------------------------


class SettingGroup(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Named setting group / bank on a relay (e.g. Group 1, Group 2)."""

    __tablename__ = "setting_groups"
    __table_args__ = (
        UniqueConstraint(
            "relay_id", "group_number", name="uq_setting_groups_relay_number"
        ),
        Index("ix_setting_groups_relay_id", "relay_id"),
    )

    relay_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("relays.id", ondelete="CASCADE"), nullable=False
    )
    group_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Any] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    relay: Mapped[Relay] = relationship("Relay", back_populates="setting_groups")
    settings: Mapped[list[Setting]] = relationship(
        "Setting", back_populates="setting_group_ref"
    )
    versions: Mapped[list[SettingVersion]] = relationship(
        "SettingVersion", back_populates="setting_group_ref"
    )


class SettingVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Immutable snapshot / version of a relay setting package."""

    __tablename__ = "setting_versions"
    __table_args__ = (
        UniqueConstraint(
            "relay_id", "version_label", name="uq_setting_versions_relay_label"
        ),
        Index("ix_setting_versions_relay_id", "relay_id"),
        Index("ix_setting_versions_approval_status", "approval_status"),
    )

    relay_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("relays.id", ondelete="CASCADE"), nullable=False
    )
    setting_group_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("setting_groups.id", ondelete="SET NULL"), nullable=True
    )
    version_label: Mapped[str] = mapped_column(String(64), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[Any] = mapped_column(
        String(128), nullable=True
    )  # file import, manual, vendor tool
    source_file_key: Mapped[Any] = mapped_column(String(512), nullable=True)
    approval_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="DRAFT"
    )
    approved_by: Mapped[Any] = mapped_column(String(36), nullable=True)
    approved_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_from: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_to: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    checksum_sha256: Mapped[Any] = mapped_column(String(64), nullable=True)
    notes: Mapped[Any] = mapped_column(Text, nullable=True)
    payload: Mapped[Any] = mapped_column(JSON, nullable=True)

    relay: Mapped[Relay] = relationship("Relay", back_populates="setting_versions")
    setting_group_ref: Mapped[Any] = relationship(
        "SettingGroup", back_populates="versions"
    )
    settings: Mapped[list[Setting]] = relationship(
        "Setting", back_populates="setting_version"
    )


class Setting(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Individual relay setting parameter row."""

    __tablename__ = "settings"
    __table_args__ = (
        Index("ix_settings_setting_id", "setting_id", unique=True),
        Index("ix_settings_relay_id", "relay_id"),
        Index("ix_settings_parameter", "parameter"),
        Index("ix_settings_approval_status", "approval_status"),
        Index("ix_settings_effective", "effective_from", "effective_to"),
    )

    setting_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=generate_uuid
    )
    relay_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("relays.id", ondelete="CASCADE"), nullable=False
    )
    setting_group_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("setting_groups.id", ondelete="SET NULL"), nullable=True
    )
    setting_version_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("setting_versions.id", ondelete="SET NULL"), nullable=True
    )
    setting_group: Mapped[Any] = mapped_column(
        String(64), nullable=True
    )  # denormalized group label for quick lookup
    parameter: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[Any] = mapped_column(Text, nullable=True)
    unit: Mapped[Any] = mapped_column(String(64), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    effective_from: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    effective_to: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    source: Mapped[Any] = mapped_column(String(128), nullable=True)
    approval_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="DRAFT"
    )
    element: Mapped[Any] = mapped_column(
        String(64), nullable=True
    )  # 21Z1, 50P1, 67N, ...
    notes: Mapped[Any] = mapped_column(Text, nullable=True)
    raw: Mapped[Any] = mapped_column(JSON, nullable=True)

    relay: Mapped[Relay] = relationship("Relay", back_populates="settings")
    setting_group_ref: Mapped[Any] = relationship(
        "SettingGroup", back_populates="settings"
    )
    setting_version: Mapped[Any] = relationship(
        "SettingVersion", back_populates="settings"
    )


# ---------------------------------------------------------------------------
# Events & files
# ---------------------------------------------------------------------------


class Event(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Protection disturbance / fault event under analysis."""

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_event_id", "event_id", unique=True),
        Index("ix_events_event_datetime", "event_datetime"),
        Index("ix_events_status", "status"),
        Index("ix_events_substation_id", "substation_id"),
        Index("ix_events_bay_id", "bay_id"),
        Index("ix_events_relay_id", "relay_id"),
    )

    event_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=generate_uuid
    )  # business identifier
    substation_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("substations.id", ondelete="SET NULL"), nullable=True
    )
    bay_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("bays.id", ondelete="SET NULL"), nullable=True
    )
    asset_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    relay_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("relays.id", ondelete="SET NULL"), nullable=True
    )
    breaker_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("breakers.id", ondelete="SET NULL"), nullable=True
    )
    engineer_id: Mapped[Any] = mapped_column(
        String(36), nullable=True
    )  # auth user id (no cross-DB FK)
    feeder: Mapped[Any] = mapped_column(String(255), nullable=True)
    event_datetime: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    nominal_voltage_kv: Mapped[Any] = mapped_column(Float, nullable=True)
    nominal_frequency_hz: Mapped[Any] = mapped_column(
        Float, nullable=True, default=50.0
    )
    description: Mapped[Any] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UPLOADED"
    )  # UPLOADED, PARSING, ANALYZING, REVIEW, CLOSED, ...
    decision_state: Mapped[Any] = mapped_column(String(64), nullable=True)
    data_quality: Mapped[Any] = mapped_column(String(32), nullable=True)
    tags: Mapped[Any] = mapped_column(JSON, nullable=True)
    extra: Mapped[Any] = mapped_column(JSON, nullable=True)

    substation: Mapped[Any] = relationship(
        "Substation", back_populates="events"
    )
    bay: Mapped[Any] = relationship("Bay", back_populates="events")
    asset: Mapped[Any] = relationship("Asset", back_populates="events")
    relay: Mapped[Any] = relationship("Relay", back_populates="events")
    breaker: Mapped[Any] = relationship(
        "Breaker", back_populates="events"
    )
    files: Mapped[list[EventFile]] = relationship(
        "EventFile", back_populates="event", cascade="all, delete-orphan"
    )
    comtrade_files: Mapped[list[ComtradeFile]] = relationship(
        "ComtradeFile", back_populates="event", cascade="all, delete-orphan"
    )
    measurements: Mapped[list[Measurement]] = relationship(
        "Measurement", back_populates="event", cascade="all, delete-orphan"
    )
    timeline_entries: Mapped[list[EventTimeline]] = relationship(
        "EventTimeline", back_populates="event", cascade="all, delete-orphan"
    )
    protection_operations: Mapped[list[ProtectionOperation]] = relationship(
        "ProtectionOperation", back_populates="event", cascade="all, delete-orphan"
    )
    consistency_findings: Mapped[list[ConsistencyFinding]] = relationship(
        "ConsistencyFinding", back_populates="event", cascade="all, delete-orphan"
    )
    fault_classifications: Mapped[list[FaultClassification]] = relationship(
        "FaultClassification", back_populates="event", cascade="all, delete-orphan"
    )
    anomalies: Mapped[list[Anomaly]] = relationship(
        "Anomaly", back_populates="event", cascade="all, delete-orphan"
    )
    rca_hypotheses: Mapped[list[RcaHypothesis]] = relationship(
        "RcaHypothesis", back_populates="event", cascade="all, delete-orphan"
    )
    evidence_items: Mapped[list[Evidence]] = relationship(
        "Evidence", back_populates="event", cascade="all, delete-orphan"
    )
    similar_as_source: Mapped[list[SimilarEvent]] = relationship(
        "SimilarEvent",
        back_populates="event",
        foreign_keys="SimilarEvent.event_id",
        cascade="all, delete-orphan",
    )
    documents: Mapped[list[Document]] = relationship(
        "Document", back_populates="event", cascade="all, delete-orphan"
    )
    reports: Mapped[list[Report]] = relationship(
        "Report", back_populates="event", cascade="all, delete-orphan"
    )
    engineer_reviews: Mapped[list[EngineerReview]] = relationship(
        "EngineerReview", back_populates="event", cascade="all, delete-orphan"
    )
    analysis_jobs: Mapped[list[AnalysisJob]] = relationship(
        "AnalysisJob", back_populates="event", cascade="all, delete-orphan"
    )


class EventFile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Immutable uploaded file belonging to an event.

    storage_key + sha256 identify content; never overwrite existing rows.
    """

    __tablename__ = "event_files"
    __table_args__ = (
        Index("ix_event_files_event_id", "event_id"),
        Index("ix_event_files_sha256", "sha256"),
        Index("ix_event_files_storage_key", "storage_key", unique=True),
        UniqueConstraint("event_id", "sha256", name="uq_event_files_event_sha256"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # COMTRADE, RELAY_EVENT_REPORT, SETTINGS, SOE, SCADA, OTHER
    content_type: Mapped[Any] = mapped_column(String(128), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    upload_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    immutable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    uploaded_by: Mapped[Any] = mapped_column(String(36), nullable=True)
    file_metadata: Mapped[Any] = mapped_column(JSON, nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="files")
    comtrade_files: Mapped[list[ComtradeFile]] = relationship(
        "ComtradeFile", back_populates="event_file"
    )


class ComtradeFile(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Parsed COMTRADE record metadata (CFG/DAT/CFF association)."""

    __tablename__ = "comtrade_files"
    __table_args__ = (
        Index("ix_comtrade_files_event_id", "event_id"),
        Index("ix_comtrade_files_event_file_id", "event_file_id"),
        Index("ix_comtrade_files_station_name", "station_name"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    event_file_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("event_files.id", ondelete="SET NULL"), nullable=True
    )
    station_name: Mapped[Any] = mapped_column(String(255), nullable=True)
    recording_device: Mapped[Any] = mapped_column(String(255), nullable=True)
    revision_year: Mapped[Any] = mapped_column(Integer, nullable=True)
    start_timestamp: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    trigger_timestamp: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sample_rate_hz: Mapped[Any] = mapped_column(Float, nullable=True)
    total_samples: Mapped[Any] = mapped_column(Integer, nullable=True)
    analog_channel_count: Mapped[Any] = mapped_column(Integer, nullable=True)
    digital_channel_count: Mapped[Any] = mapped_column(Integer, nullable=True)
    frequency_hz: Mapped[Any] = mapped_column(Float, nullable=True)
    line_frequency_hz: Mapped[Any] = mapped_column(Float, nullable=True)
    cfg_storage_key: Mapped[Any] = mapped_column(String(512), nullable=True)
    dat_storage_key: Mapped[Any] = mapped_column(String(512), nullable=True)
    hdr_storage_key: Mapped[Any] = mapped_column(String(512), nullable=True)
    inf_storage_key: Mapped[Any] = mapped_column(String(512), nullable=True)
    parser_version: Mapped[Any] = mapped_column(String(32), nullable=True)
    validation_status: Mapped[Any] = mapped_column(String(64), nullable=True)
    data_quality: Mapped[Any] = mapped_column(String(32), nullable=True)
    parse_warnings: Mapped[Any] = mapped_column(JSON, nullable=True)
    header_metadata: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )

    event: Mapped[Event] = relationship("Event", back_populates="comtrade_files")
    event_file: Mapped[Any] = relationship(
        "EventFile", back_populates="comtrade_files"
    )
    channels: Mapped[list[ComtradeChannel]] = relationship(
        "ComtradeChannel",
        back_populates="comtrade_file",
        cascade="all, delete-orphan",
    )


class ComtradeChannel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Analog or digital channel definition from a COMTRADE file."""

    __tablename__ = "comtrade_channels"
    __table_args__ = (
        UniqueConstraint(
            "comtrade_file_id",
            "channel_index",
            "channel_type",
            name="uq_comtrade_channels_file_idx_type",
        ),
        Index("ix_comtrade_channels_comtrade_file_id", "comtrade_file_id"),
        Index("ix_comtrade_channels_name", "name"),
    )

    comtrade_file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("comtrade_files.id", ondelete="CASCADE"), nullable=False
    )
    channel_index: Mapped[int] = mapped_column(Integer, nullable=False)
    channel_type: Mapped[str] = mapped_column(
        String(16), nullable=False
    )  # ANALOG | DIGITAL
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    phase: Mapped[Any] = mapped_column(String(16), nullable=True)
    units: Mapped[Any] = mapped_column(String(32), nullable=True)
    secondary: Mapped[Any] = mapped_column(Boolean, nullable=True)
    multiplier: Mapped[Any] = mapped_column(Float, nullable=True)
    offset: Mapped[Any] = mapped_column(Float, nullable=True)
    skew: Mapped[Any] = mapped_column(Float, nullable=True)
    min_value: Mapped[Any] = mapped_column(Float, nullable=True)
    max_value: Mapped[Any] = mapped_column(Float, nullable=True)
    primary: Mapped[Any] = mapped_column(Float, nullable=True)
    secondary_ratio: Mapped[Any] = mapped_column(Float, nullable=True)
    ps: Mapped[Any] = mapped_column(String(8), nullable=True)  # P or S
    normal_state: Mapped[Any] = mapped_column(
        Integer, nullable=True
    )  # digital
    mapped_signal: Mapped[Any] = mapped_column(
        String(128), nullable=True
    )  # Ia, Ib, Ic, Va, ...
    channel_metadata: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )

    comtrade_file: Mapped[ComtradeFile] = relationship(
        "ComtradeFile", back_populates="channels"
    )
    measurements: Mapped[list[Measurement]] = relationship(
        "Measurement", back_populates="channel"
    )


# ---------------------------------------------------------------------------
# Measurements, timeline, protection operations
# ---------------------------------------------------------------------------


class Measurement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Derived or extracted measurement for an event (RMS, phasor, impedance, etc.)."""

    __tablename__ = "measurements"
    __table_args__ = (
        Index("ix_measurements_event_id", "event_id"),
        Index("ix_measurements_channel_id", "channel_id"),
        Index("ix_measurements_quantity", "quantity"),
        Index("ix_measurements_timestamp", "timestamp"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    channel_id: Mapped[Any] = mapped_column(
        String(36),
        ForeignKey("comtrade_channels.id", ondelete="SET NULL"),
        nullable=True,
    )
    quantity: Mapped[str] = mapped_column(
        String(128), nullable=False
    )  # Ia_rms, Vab_mag, Z_mag, freq, ...
    phase: Mapped[Any] = mapped_column(String(16), nullable=True)
    value: Mapped[Any] = mapped_column(Float, nullable=True)
    unit: Mapped[Any] = mapped_column(String(32), nullable=True)
    timestamp: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sample_index: Mapped[Any] = mapped_column(Integer, nullable=True)
    window_start_us: Mapped[Any] = mapped_column(Integer, nullable=True)
    window_end_us: Mapped[Any] = mapped_column(Integer, nullable=True)
    algorithm: Mapped[Any] = mapped_column(String(64), nullable=True)
    algorithm_version: Mapped[Any] = mapped_column(String(32), nullable=True)
    quality: Mapped[Any] = mapped_column(String(32), nullable=True)
    vector: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )  # mag/angle or multi-component
    extra: Mapped[Any] = mapped_column(JSON, nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="measurements")
    channel: Mapped[Any] = relationship(
        "ComtradeChannel", back_populates="measurements"
    )


class EventTimeline(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Ordered timeline entry reconstructing the disturbance sequence."""

    __tablename__ = "event_timeline"
    __table_args__ = (
        Index("ix_event_timeline_event_id", "event_id"),
        Index("ix_event_timeline_event_time", "event_id", "t_us"),
        Index("ix_event_timeline_event_type", "event_type"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    t_us: Mapped[Any] = mapped_column(
        Integer, nullable=True
    )  # microseconds relative to trigger / start
    absolute_time: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    event_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # FAULT_INCEPTION, PICKUP, TRIP, BREAKER_OPEN, ...
    source: Mapped[Any] = mapped_column(String(64), nullable=True)
    label: Mapped[Any] = mapped_column(String(255), nullable=True)
    description: Mapped[Any] = mapped_column(Text, nullable=True)
    confidence: Mapped[Any] = mapped_column(Float, nullable=True)
    evidence_ids: Mapped[Any] = mapped_column(JSON, nullable=True)
    payload: Mapped[Any] = mapped_column(JSON, nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="timeline_entries")


class ProtectionOperation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Observed or inferred protection element operation for an event."""

    __tablename__ = "protection_operations"
    __table_args__ = (
        Index("ix_protection_operations_event_id", "event_id"),
        Index("ix_protection_operations_relay_id", "relay_id"),
        Index("ix_protection_operations_element", "element"),
        Index("ix_protection_operations_function_code", "function_code"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    relay_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("relays.id", ondelete="SET NULL"), nullable=True
    )
    breaker_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("breakers.id", ondelete="SET NULL"), nullable=True
    )
    element: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # Z1, 50P1, 67N, BF, ...
    function_code: Mapped[Any] = mapped_column(
        String(32), nullable=True
    )  # ANSI / IEC code
    operation_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # PICKUP, TRIP, TARGET, BLOCK, RECLOSE, ...
    asserted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    t_pickup_us: Mapped[Any] = mapped_column(Integer, nullable=True)
    t_trip_us: Mapped[Any] = mapped_column(Integer, nullable=True)
    t_reset_us: Mapped[Any] = mapped_column(Integer, nullable=True)
    absolute_pickup: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    absolute_trip: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expected: Mapped[Any] = mapped_column(Boolean, nullable=True)
    breaker_assessment: Mapped[Any] = mapped_column(String(32), nullable=True)
    confidence: Mapped[Any] = mapped_column(Float, nullable=True)
    evidence_ids: Mapped[Any] = mapped_column(JSON, nullable=True)
    details: Mapped[Any] = mapped_column(JSON, nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="protection_operations")
    relay: Mapped[Any] = relationship(
        "Relay", back_populates="protection_operations"
    )
    breaker: Mapped[Any] = relationship(
        "Breaker", back_populates="protection_operations"
    )


# ---------------------------------------------------------------------------
# Analysis results
# ---------------------------------------------------------------------------


class ConsistencyFinding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Setting vs observed behaviour consistency check result.

    Fields align with ConsistencyFinding domain object:
    finding_id, event_id, element, check_type, setting_source, setting_version,
    expected, observed, status, severity, evidence_ids, explanation, confidence.
    """

    __tablename__ = "consistency_findings"
    __table_args__ = (
        Index("ix_consistency_findings_finding_id", "finding_id", unique=True),
        Index("ix_consistency_findings_event_id", "event_id"),
        Index("ix_consistency_findings_element", "element"),
        Index("ix_consistency_findings_status", "status"),
        Index("ix_consistency_findings_severity", "severity"),
    )

    finding_id: Mapped[str] = mapped_column(
        String(64), nullable=False, default=generate_uuid
    )
    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    element: Mapped[str] = mapped_column(String(64), nullable=False)
    check_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # PICKUP_THRESHOLD, ZONE_REACH, TIME_DELAY, DIRECTION, ...
    setting_source: Mapped[Any] = mapped_column(String(128), nullable=True)
    setting_version: Mapped[Any] = mapped_column(String(64), nullable=True)
    expected: Mapped[Any] = mapped_column(JSON, nullable=True)
    observed: Mapped[Any] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # CONSISTENT, INCONSISTENT, UNVERIFIABLE, DATA_QUALITY_ISSUE
    severity: Mapped[str] = mapped_column(
        String(32), nullable=False, default="INFO"
    )
    evidence_ids: Mapped[Any] = mapped_column(JSON, nullable=True)
    explanation: Mapped[Any] = mapped_column(Text, nullable=True)
    confidence: Mapped[Any] = mapped_column(Float, nullable=True)
    rule_version: Mapped[Any] = mapped_column(String(32), nullable=True)
    extra: Mapped[Any] = mapped_column(JSON, nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="consistency_findings")


class FaultClassification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Fault type / location classification for an event."""

    __tablename__ = "fault_classifications"
    __table_args__ = (
        Index("ix_fault_classifications_event_id", "event_id"),
        Index("ix_fault_classifications_fault_type", "fault_type"),
        Index("ix_fault_classifications_status", "status"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    fault_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNKNOWN"
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="UNKNOWN"
    )
    involved_phases: Mapped[Any] = mapped_column(JSON, nullable=True)
    ground_involved: Mapped[Any] = mapped_column(Boolean, nullable=True)
    distance_km: Mapped[Any] = mapped_column(Float, nullable=True)
    distance_pu: Mapped[Any] = mapped_column(Float, nullable=True)
    location_method: Mapped[Any] = mapped_column(String(64), nullable=True)
    impedance_ohm: Mapped[Any] = mapped_column(Float, nullable=True)
    impedance_angle_deg: Mapped[Any] = mapped_column(Float, nullable=True)
    resistance_ohm: Mapped[Any] = mapped_column(Float, nullable=True)
    inception_t_us: Mapped[Any] = mapped_column(Integer, nullable=True)
    clearing_t_us: Mapped[Any] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[Any] = mapped_column(Float, nullable=True)
    confidence: Mapped[Any] = mapped_column(Float, nullable=True)
    confidence_level: Mapped[Any] = mapped_column(String(32), nullable=True)
    classifier_version: Mapped[Any] = mapped_column(String(32), nullable=True)
    evidence_ids: Mapped[Any] = mapped_column(JSON, nullable=True)
    explanation: Mapped[Any] = mapped_column(Text, nullable=True)
    features: Mapped[Any] = mapped_column(JSON, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    event: Mapped[Event] = relationship("Event", back_populates="fault_classifications")


class Anomaly(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Detected anomaly during signal processing or protection analysis."""

    __tablename__ = "anomalies"
    __table_args__ = (
        Index("ix_anomalies_event_id", "event_id"),
        Index("ix_anomalies_anomaly_type", "anomaly_type"),
        Index("ix_anomalies_severity", "severity"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    anomaly_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False, default="MEDIUM")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Any] = mapped_column(Text, nullable=True)
    t_us: Mapped[Any] = mapped_column(Integer, nullable=True)
    channel_name: Mapped[Any] = mapped_column(String(128), nullable=True)
    detector: Mapped[Any] = mapped_column(String(64), nullable=True)
    confidence: Mapped[Any] = mapped_column(Float, nullable=True)
    evidence_ids: Mapped[Any] = mapped_column(JSON, nullable=True)
    details: Mapped[Any] = mapped_column(JSON, nullable=True)
    acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    event: Mapped[Event] = relationship("Event", back_populates="anomalies")


class RcaHypothesis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Root-cause analysis hypothesis ranked for an event."""

    __tablename__ = "rca_hypotheses"
    __table_args__ = (
        Index("ix_rca_hypotheses_event_id", "event_id"),
        Index("ix_rca_hypotheses_status", "status"),
        Index("ix_rca_hypotheses_rank", "event_id", "rank"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    hypothesis_code: Mapped[Any] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="POSSIBLE"
    )
    rank: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    confidence: Mapped[Any] = mapped_column(Float, nullable=True)
    confidence_level: Mapped[Any] = mapped_column(String(32), nullable=True)
    supporting_evidence_ids: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )
    contradicting_evidence_ids: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )
    causal_chain: Mapped[Any] = mapped_column(JSON, nullable=True)
    recommended_actions: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )
    engine_version: Mapped[Any] = mapped_column(String(32), nullable=True)
    explanation: Mapped[Any] = mapped_column(Text, nullable=True)
    extra: Mapped[Any] = mapped_column(JSON, nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="rca_hypotheses")
    evidence_links: Mapped[list[Evidence]] = relationship(
        "Evidence", back_populates="hypothesis"
    )


class Evidence(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Evidence item supporting or contradicting findings / hypotheses."""

    __tablename__ = "evidence"
    __table_args__ = (
        Index("ix_evidence_event_id", "event_id"),
        Index("ix_evidence_hypothesis_id", "hypothesis_id"),
        Index("ix_evidence_source_type", "source_type"),
        Index("ix_evidence_evidence_key", "evidence_key"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    hypothesis_id: Mapped[Any] = mapped_column(
        String(36),
        ForeignKey("rca_hypotheses.id", ondelete="SET NULL"),
        nullable=True,
    )
    evidence_key: Mapped[str] = mapped_column(
        String(64), nullable=False, default=generate_uuid
    )
    source_type: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # COMTRADE, BASE_SETTINGS, PROTECTION_RULE, ...
    polarity: Mapped[str] = mapped_column(
        String(32), nullable=False, default="SUPPORTING"
    )  # SUPPORTING | CONTRADICTING | NEUTRAL
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[Any] = mapped_column(Text, nullable=True)
    confidence: Mapped[Any] = mapped_column(Float, nullable=True)
    t_us: Mapped[Any] = mapped_column(Integer, nullable=True)
    references: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )  # file/channel/setting pointers
    graph_node: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )  # evidence graph fragment
    raw: Mapped[Any] = mapped_column(JSON, nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="evidence_items")
    hypothesis: Mapped[Any] = relationship(
        "RcaHypothesis", back_populates="evidence_links"
    )


class SimilarEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Link between an event and a historically similar disturbance."""

    __tablename__ = "similar_events"
    __table_args__ = (
        UniqueConstraint(
            "event_id", "similar_event_id", name="uq_similar_events_pair"
        ),
        Index("ix_similar_events_event_id", "event_id"),
        Index("ix_similar_events_similar_event_id", "similar_event_id"),
        Index("ix_similar_events_score", "similarity_score"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    similar_event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    similarity_score: Mapped[float] = mapped_column(Float, nullable=False)
    method: Mapped[Any] = mapped_column(String(64), nullable=True)
    matched_features: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )
    notes: Mapped[Any] = mapped_column(Text, nullable=True)

    event: Mapped[Event] = relationship(
        "Event",
        back_populates="similar_as_source",
        foreign_keys=[event_id],
    )
    similar_event: Mapped[Event] = relationship(
        "Event",
        foreign_keys=[similar_event_id],
    )


# ---------------------------------------------------------------------------
# Documents, reports, reviews
# ---------------------------------------------------------------------------


class Document(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Supporting document attached to an event or asset (PDF, drawings, notes)."""

    __tablename__ = "documents"
    __table_args__ = (
        Index("ix_documents_event_id", "event_id"),
        Index("ix_documents_document_type", "document_type"),
        Index("ix_documents_storage_key", "storage_key", unique=True),
    )

    event_id: Mapped[Any] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=True
    )
    uploaded_by: Mapped[Any] = mapped_column(
        String(36), nullable=True
    )  # auth user id (no cross-DB FK)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    document_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="OTHER"
    )
    original_filename: Mapped[Any] = mapped_column(String(512), nullable=True)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[Any] = mapped_column(String(64), nullable=True)
    file_size: Mapped[Any] = mapped_column(Integer, nullable=True)
    content_type: Mapped[Any] = mapped_column(String(128), nullable=True)
    description: Mapped[Any] = mapped_column(Text, nullable=True)
    tags: Mapped[Any] = mapped_column(JSON, nullable=True)
    extra: Mapped[Any] = mapped_column(JSON, nullable=True)

    event: Mapped[Any] = relationship("Event", back_populates="documents")


class Report(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Generated RCA / disturbance analysis report."""

    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_event_id", "event_id"),
        Index("ix_reports_status", "status"),
        Index("ix_reports_report_type", "report_type"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    report_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="RCA"
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="DRAFT"
    )  # DRAFT, FINAL, ARCHIVED
    template_version: Mapped[Any] = mapped_column(String(32), nullable=True)
    storage_key: Mapped[Any] = mapped_column(String(512), nullable=True)
    format: Mapped[Any] = mapped_column(
        String(16), nullable=True
    )  # PDF, HTML, JSON
    summary: Mapped[Any] = mapped_column(Text, nullable=True)
    sections: Mapped[Any] = mapped_column(JSON, nullable=True)
    generated_by: Mapped[Any] = mapped_column(String(36), nullable=True)
    generated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    extra: Mapped[Any] = mapped_column(JSON, nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="reports")


class EngineerReview(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Human engineer review / disposition of automated analysis."""

    __tablename__ = "engineer_reviews"
    __table_args__ = (
        Index("ix_engineer_reviews_event_id", "event_id"),
        Index("ix_engineer_reviews_reviewer_id", "reviewer_id"),
        Index("ix_engineer_reviews_action", "action"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    reviewer_id: Mapped[Any] = mapped_column(
        String(36), nullable=True
    )  # auth user id (no cross-DB FK)
    action: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # ACCEPT, MODIFY, REJECT, INCONCLUSIVE, REQUEST_FIELD_INVESTIGATION
    decision_state: Mapped[Any] = mapped_column(String(64), nullable=True)
    comments: Mapped[Any] = mapped_column(Text, nullable=True)
    modifications: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )  # corrected fault type, hypothesis, etc.
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    extra: Mapped[Any] = mapped_column(JSON, nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="engineer_reviews")


# ---------------------------------------------------------------------------
# Governance: audit, rule/model versions, analysis jobs
# ---------------------------------------------------------------------------


class AuditLog(Base, UUIDPrimaryKeyMixin):
    """Immutable audit trail of user and system actions."""

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("ix_audit_log_user_id", "user_id"),
        Index("ix_audit_log_timestamp", "timestamp"),
        Index("ix_audit_log_action", "action"),
        Index("ix_audit_log_object_type_id", "object_type", "object_id"),
    )

    user_id: Mapped[Any] = mapped_column(
        String(36), nullable=True
    )  # auth user id (no cross-DB FK)
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    action: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # CREATE, UPDATE, DELETE, LOGIN, APPROVE, EXPORT, ...
    object_type: Mapped[Any] = mapped_column(String(64), nullable=True)
    object_id: Mapped[Any] = mapped_column(String(64), nullable=True)
    old_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    ip_address: Mapped[Any] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Any] = mapped_column(String(512), nullable=True)
    request_id: Mapped[Any] = mapped_column(String(64), nullable=True)
    metadata_json: Mapped[Any] = mapped_column(
        "metadata", JSON, nullable=True
    )


class RuleVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Versioned protection / consistency / RCA rule package."""

    __tablename__ = "rule_versions"
    __table_args__ = (
        UniqueConstraint(
            "rule_family", "version", name="uq_rule_versions_family_version"
        ),
        Index("ix_rule_versions_rule_family", "rule_family"),
        Index("ix_rule_versions_is_active", "is_active"),
    )

    rule_family: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # PROTECTION, CONSISTENCY, RCA, SIGNAL
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Any] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checksum_sha256: Mapped[Any] = mapped_column(String(64), nullable=True)
    storage_key: Mapped[Any] = mapped_column(String(512), nullable=True)
    rules_payload: Mapped[Any] = mapped_column(JSON, nullable=True)
    activated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[Any] = mapped_column(String(36), nullable=True)


class ModelVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Versioned ML / statistical model artifact used in analysis."""

    __tablename__ = "model_versions"
    __table_args__ = (
        UniqueConstraint(
            "model_name", "version", name="uq_model_versions_name_version"
        ),
        Index("ix_model_versions_model_name", "model_name"),
        Index("ix_model_versions_is_active", "is_active"),
    )

    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_type: Mapped[Any] = mapped_column(
        String(64), nullable=True
    )  # CLASSIFIER, ANOMALY, SIMILARITY, ...
    description: Mapped[Any] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    framework: Mapped[Any] = mapped_column(String(64), nullable=True)
    storage_key: Mapped[Any] = mapped_column(String(512), nullable=True)
    checksum_sha256: Mapped[Any] = mapped_column(String(64), nullable=True)
    metrics: Mapped[Any] = mapped_column(JSON, nullable=True)
    hyperparameters: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )
    trained_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    activated_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by: Mapped[Any] = mapped_column(String(36), nullable=True)


class AnalysisJob(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """Async analysis pipeline job with stage progress and error tracking."""

    __tablename__ = "analysis_jobs"
    __table_args__ = (
        Index("ix_analysis_jobs_event_id", "event_id"),
        Index("ix_analysis_jobs_status", "status"),
        Index("ix_analysis_jobs_stage", "stage"),
        Index("ix_analysis_jobs_requested_by", "requested_by"),
        Index("ix_analysis_jobs_celery_task_id", "celery_task_id"),
    )

    event_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[Any] = mapped_column(
        String(36), nullable=True
    )  # auth user id (no cross-DB FK)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING"
    )  # PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
    stage: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UPLOAD"
    )  # JobStage enum values
    progress: Mapped[float] = mapped_column(
        Float, nullable=False, default=0.0
    )  # 0.0 – 100.0
    stages: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )  # [{name, status, started_at, finished_at, message}, ...]
    current_message: Mapped[Any] = mapped_column(Text, nullable=True)
    error_message: Mapped[Any] = mapped_column(Text, nullable=True)
    error_details: Mapped[Any] = mapped_column(JSON, nullable=True)
    celery_task_id: Mapped[Any] = mapped_column(String(64), nullable=True)
    started_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[Any] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    component_versions: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )  # parser/rules/model versions used
    result_summary: Mapped[Any] = mapped_column(
        JSON, nullable=True
    )
    parameters: Mapped[Any] = mapped_column(JSON, nullable=True)

    event: Mapped[Event] = relationship("Event", back_populates="analysis_jobs")


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "User",
    "Role",
    "Substation",
    "VoltageLevel",
    "Bay",
    "Feeder",
    "Asset",
    "Relay",
    "Breaker",
    "SettingGroup",
    "SettingVersion",
    "Setting",
    "Event",
    "EventFile",
    "ComtradeFile",
    "ComtradeChannel",
    "Measurement",
    "EventTimeline",
    "ProtectionOperation",
    "ConsistencyFinding",
    "FaultClassification",
    "Anomaly",
    "RcaHypothesis",
    "Evidence",
    "SimilarEvent",
    "Document",
    "Report",
    "EngineerReview",
    "AuditLog",
    "RuleVersion",
    "ModelVersion",
    "AnalysisJob",
    "generate_uuid",
]
