"""Optional bootstrap only — no demo events, assets, or sample data.

When the users table is empty, creates a first admin:

  BOOTSTRAP_ADMIN_USERNAME (default: admin)
  BOOTSTRAP_ADMIN_PASSWORD (default: admin123 for local/portable)
  BOOTSTRAP_ADMIN_EMAIL    (default: admin@example.com)

Set BOOTSTRAP_ADMIN_PASSWORD empty and BOOTSTRAP_SKIP=1 to skip auto-create.
Never invents substations, relays, events, or engineering defaults.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import func, select

from app.core.security import Role, hash_password
from app.database import AuthSessionLocal
from app.models import User

logger = logging.getLogger(__name__)


def _bootstrap_credentials() -> tuple[str, str, str] | None:
    if os.getenv("BOOTSTRAP_SKIP", "").strip().lower() in ("1", "true", "yes"):
        return None
    username = (os.getenv("BOOTSTRAP_ADMIN_USERNAME") or "admin").strip()
    # Explicit empty password means "do not bootstrap" when username was customized
    # without password; default local password when unset.
    raw_pw = os.getenv("BOOTSTRAP_ADMIN_PASSWORD")
    if raw_pw is None or raw_pw == "":
        # Local / portable convenience (documented in SECURITY.md)
        password = "admin123"
    else:
        password = raw_pw
    if not username or not password:
        return None
    email = (os.getenv("BOOTSTRAP_ADMIN_EMAIL") or f"{username}@example.com").strip()
    return username, password, email


async def seed_if_empty() -> None:
    """No default domain data. Optional admin bootstrap only."""
    creds = _bootstrap_credentials()
    if creds is None:
        logger.info(
            "Bootstrap skipped — set BOOTSTRAP_ADMIN_USERNAME/PASSWORD "
            "or unset BOOTSTRAP_SKIP to create the first admin."
        )
        return

    username, password, email = creds

    async with AuthSessionLocal() as db:
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
