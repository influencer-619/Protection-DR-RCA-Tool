"""Aggregate all API routers. No OT control endpoints are registered."""

from fastapi import APIRouter

from app.api import (
    analysis,
    assets,
    audit,
    auth,
    comtrade,
    dashboard,
    events,
    files,
    models_api,
    reports,
    review,
    rules,
    settings,
    users,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(events.router)
api_router.include_router(files.router)
api_router.include_router(comtrade.router)
api_router.include_router(settings.router)
api_router.include_router(analysis.router)
api_router.include_router(reports.router)
api_router.include_router(review.router)
api_router.include_router(assets.router)
api_router.include_router(rules.router)
api_router.include_router(models_api.router)
api_router.include_router(audit.router)
api_router.include_router(dashboard.router)
api_router.include_router(users.router)
