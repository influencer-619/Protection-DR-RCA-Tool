"""Reusable column mixins for SQLAlchemy ORM models."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column


def generate_uuid() -> str:
    """Return a new UUID4 string suitable for String(36) primary keys."""
    return str(uuid4())


class TimestampMixin:
    """created_at / updated_at columns with timezone-aware UTC defaults."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class UUIDPrimaryKeyMixin:
    """String UUID primary key (36 chars including hyphens)."""

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
