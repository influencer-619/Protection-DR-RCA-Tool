"""SQLAlchemy async database setup — app data DB + separate auth (users) DB."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(DeclarativeBase):
    """Plant / events / analysis tables."""


class AuthBase(DeclarativeBase):
    """Users / credentials only — survives clearing the app data DB."""


def _default_auth_database_url(main_url: str) -> str:
    """Sibling SQLite auth file, or same URL for non-SQLite unless overridden."""
    raw = (main_url or "").strip()
    if "sqlite" not in raw:
        return raw
    # sqlite+aiosqlite:///C:/path/file.db  or  sqlite+aiosqlite:////absolute
    marker = ":///"
    idx = raw.find(marker)
    if idx < 0:
        return raw
    path_part = raw[idx + len(marker) :]
    # Windows: D:/... ; Unix absolute may start with /
    p = Path(path_part)
    auth_path = p.with_name("protection_rca_auth.db")
    return f"{raw[: idx + len(marker)]}{auth_path.as_posix()}"


settings = get_settings()
_auth_url = (settings.auth_database_url or "").strip() or _default_auth_database_url(
    settings.database_url
)

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,
)
auth_engine = create_async_engine(
    _auth_url,
    echo=settings.debug,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)
AuthSessionLocal = async_sessionmaker(
    auth_engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_auth_db() -> AsyncGenerator[AsyncSession, None]:
    async with AuthSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _sqlite_add_missing_columns(connection) -> None:
    """Add nullable columns introduced after initial create_all (SQLite only)."""
    dialect = connection.dialect.name
    if dialect != "sqlite":
        return

    patches: list[tuple[str, str, str]] = [
        ("bays", "voltage_level_id", "VARCHAR(36)"),
        ("relays", "feeder_id", "VARCHAR(36)"),
    ]
    for table, column, coltype in patches:
        rows = connection.execute(text(f"PRAGMA table_info({table})")).fetchall()
        existing = {r[1] for r in rows}
        if not existing:
            continue
        if column not in existing:
            connection.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}")
            )


async def _migrate_users_from_app_db_if_needed() -> None:
    """One-time copy: users in old app DB → auth DB when auth is empty."""
    from sqlalchemy import func, select

    from app.models import User

    async with AuthSessionLocal() as auth_db:
        count = (
            await auth_db.execute(select(func.count()).select_from(User))
        ).scalar_one()
        if count and int(count) > 0:
            return

    # Read legacy users from app DB if table exists
    async with engine.connect() as conn:
        dialect = conn.dialect.name
        if dialect == "sqlite":
            rows = (
                await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'"))
            ).fetchall()
            if not rows:
                return
        else:
            # Best-effort: try select; ignore if missing
            try:
                await conn.execute(text("SELECT 1 FROM users LIMIT 1"))
            except Exception:
                return

    async with AsyncSessionLocal() as app_db:
        try:
            legacy = (await app_db.execute(text(
                "SELECT id, username, email, full_name, hashed_password, role, is_active, "
                "last_login_at, preferences, created_at, updated_at FROM users"
            ))).mappings().all()
        except Exception:
            return
        if not legacy:
            return

    async with AuthSessionLocal() as auth_db:
        for row in legacy:
            auth_db.add(
                User(
                    id=row["id"],
                    username=row["username"],
                    email=row["email"],
                    full_name=row.get("full_name"),
                    hashed_password=row["hashed_password"],
                    role=row.get("role") or "VIEWER",
                    is_active=bool(row.get("is_active", True)),
                    last_login_at=row.get("last_login_at"),
                    preferences=row.get("preferences"),
                )
            )
        await auth_db.commit()


async def init_db() -> None:
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_sqlite_add_missing_columns)

    async with auth_engine.begin() as conn:
        await conn.run_sync(AuthBase.metadata.create_all)

    await _migrate_users_from_app_db_if_needed()
