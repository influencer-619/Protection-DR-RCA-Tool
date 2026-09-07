"""Pydantic v2 schemas — evidence."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class EvidenceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    hypothesis_id: Optional[str] = None
    evidence_key: str
    source_type: str
    polarity: str
    title: str
    summary: Optional[str] = None
    confidence: Optional[float] = None
    t_us: Optional[int] = None
    references: Optional[dict[str, Any]] = None
    created_at: datetime


class EvidenceListResponse(BaseModel):
    event_id: str
    items: list[EvidenceOut]
