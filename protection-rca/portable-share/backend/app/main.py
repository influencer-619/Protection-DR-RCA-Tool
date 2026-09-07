"""
Protection RCA Platform — FastAPI entrypoint.

OT SAFETY: This application exposes analysis, review, and reporting APIs only.
There are no breaker trip, relay control, SCADA write, or field-device command endpoints.
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.database import init_db
from app.middleware.security import (
    RateLimitMiddleware,
    RequestIdMiddleware,
    SecurityHeadersMiddleware,
)
from app.services.seed import seed_if_empty

configure_logging()
logger = get_logger("app.main")


def _resolve_frontend_dist() -> Path | None:
    settings = get_settings()
    candidates: list[Path] = []
    if settings.frontend_dist:
        candidates.append(Path(settings.frontend_dist))
    env_dist = os.environ.get("FRONTEND_DIST", "").strip()
    if env_dist:
        candidates.append(Path(env_dist))
    # Common layouts: repo frontend/dist, or bundled next to backend
    here = Path(__file__).resolve()
    candidates.extend(
        [
            here.parents[2] / "frontend" / "dist",  # .../protection-rca/frontend/dist
            here.parents[1] / "frontend_dist",
            here.parents[1] / "static" / "ui",
        ]
    )
    serve_flag = os.environ.get("SERVE_FRONTEND", "auto").strip().lower()
    if serve_flag in ("0", "false", "no", "off"):
        return None
    force = settings.serve_frontend or serve_flag in ("1", "true", "yes", "on")
    for path in candidates:
        if path.is_dir() and (path / "index.html").is_file():
            if force or serve_flag == "auto":
                return path
    return None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    logger.info("starting", env=settings.app_env, version=settings.app_version)
    await init_db()
    await seed_if_empty()
    yield
    logger.info("shutdown")


def _mount_spa(application: FastAPI, dist: Path) -> None:
    assets = dist / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=str(assets)), name="assets")

    reserved = ("api", "docs", "redoc", "openapi.json", "health", "assets")

    @application.get("/")
    async def spa_index():
        return FileResponse(dist / "index.html")

    @application.get("/{full_path:path}")
    async def spa_fallback(full_path: str):
        first = full_path.split("/", 1)[0]
        if first in reserved or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        candidate = (dist / full_path).resolve()
        try:
            candidate.relative_to(dist.resolve())
        except ValueError:
            raise HTTPException(status_code=404, detail="Not Found") from None
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(dist / "index.html")

    logger.info("spa_mounted", path=str(dist))


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Protection Disturbance Record / COMTRADE Root Cause Analysis platform. "
            "Read-only OT-adjacent analysis — no control plane."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Inner middlewares first; CORS last so it stays outermost and still
    # tags early responses (e.g. 429) — otherwise the browser reports Network Error.
    application.add_middleware(SecurityHeadersMiddleware)
    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(RateLimitMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_origin_regex=settings.cors_origin_regex or None,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    application.include_router(api_router)

    @application.get("/health", tags=["health"])
    @application.get("/api/health", tags=["health"])
    async def health():
        return {
            "status": "ok",
            "service": settings.app_name,
            "version": settings.app_version,
            "ot_control_plane": "disabled",
        }

    dist = _resolve_frontend_dist()
    if dist is not None:
        _mount_spa(application, dist)

    return application


app = create_app()
