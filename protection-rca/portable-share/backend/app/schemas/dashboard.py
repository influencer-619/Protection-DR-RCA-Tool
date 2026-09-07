"""Dashboard schemas."""

from app.schemas.rules import (
    DashboardAttentionItem,
    DashboardDqBreakdown,
    DashboardRecentEvent,
    DashboardStats,
    DashboardTrendPoint,
)

__all__ = [
    "DashboardStats",
    "DashboardTrendPoint",
    "DashboardDqBreakdown",
    "DashboardAttentionItem",
    "DashboardRecentEvent",
]
