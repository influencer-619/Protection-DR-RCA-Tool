"""Pydantic v2 schemas — engineer review."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ReviewCreate(BaseModel):
    event_id: str
    action: str = Field(..., description="ACCEPT|MODIFY|REJECT|INCONCLUSIVE|REQUEST_FIELD_INVESTIGATION")
    decision_state: Optional[str] = None
    comments: Optional[str] = None
    modifications: Optional[dict[str, Any]] = None


class ReviewApprove(BaseModel):
    event_id: str
    comments: Optional[str] = None
    decision_state: Optional[str] = "ANALYSIS_COMPLETE"


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    reviewer_id: Optional[str] = None
    action: str
    decision_state: Optional[str] = None
    comments: Optional[str] = None
    modifications: Optional[dict[str, Any]] = None
    reviewed_at: datetime
    created_at: datetime
