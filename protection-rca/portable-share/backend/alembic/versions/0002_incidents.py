"""Add incidents / incident_members tables (Stage E).

Revision ID: 0002_incidents
Revises: 0001_initial_schema
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "0002_incidents"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Portable / SQLite apps also run Base.metadata.create_all on startup.
    # This revision ensures compose/Postgres picks up Incident tables.
    from app.database import Base
    from app import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.create_all(
        bind=bind,
        tables=[
            Base.metadata.tables["incidents"],
            Base.metadata.tables["incident_members"],
        ],
    )


def downgrade() -> None:
    op.drop_table("incident_members")
    op.drop_table("incidents")
