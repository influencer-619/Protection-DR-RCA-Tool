"""Optional bootstrap only — no demo events, assets, or sample data.

By default this does nothing. To create a first admin when the DB has no users,
set environment variables:

  BOOTSTRAP_ADMIN_USERNAME=admin
  BOOTSTRAP_ADMIN_PASSWORD=<strong-password>
  BOOTSTRAP_ADMIN_EMAIL=admin@example.com

Never invents substations, relays, events, or engineering defaults.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import func, select

from app.core.security import Role, hash_password
from app.database import AsyncSessionLocal
from app.models import User

logger = logging.getLogger(__name__)


async def seed_if_empty() -> None:
    """No default domain data. Optional admin bootstrap only."""
    username = (os.getenv("BOOTSTRAP_ADMIN_USERNAME") or "").strip()
    password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD") or ""
    if not username or not password:
        logger.info(
            "Bootstrap skipped — set BOOTSTRAP_ADMIN_USERNAME and "
            "BOOTSTRAP_ADMIN_PASSWORD to create the first admin (no demo data)."
        )
        return

    email = (os.getenv("BOOTSTRAP_ADMIN_EMAIL") or f"{username}@example.com").strip()

    async with AsyncSessionLocal() as db:
        try:
            count = (await db.execute(select(func.count()).select_from(User))).scalar_one()
            if count and int(count) > 0:
                logger.info("Bootstrap skipped — users already present (%s)", count)
                return

            db.add(
                User(
                    username=username,
                    email=email,
                    full_name=os.getenv("BOOTSTRAP_ADMIN_FULL_NAME") or "Administrator",
                    hashed_password=hash_password(password),
                    role=Role.ADMIN.value,
                    is_active=True,
                )
            )
            await db.commit()
            logger.info("Bootstrap admin created: %s (no demo domain data)", username)
        except Exception:
            await db.rollback()
            logger.exception("Bootstrap failed")
            raise
