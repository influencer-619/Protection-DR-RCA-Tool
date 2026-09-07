"""Pydantic v2 schemas — RCA hypotheses."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, model_validator


class RcaHypothesisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    hypothesis_code: Optional[str] = None
    title: str
    statement: str
    status: str
    rank: int
    confidence: Optional[float] = None
    confidence_level: Optional[str] = None
    supporting_evidence_ids: Optional[list[Any]] = None
    contradicting_evidence_ids: Optional[list[Any]] = None
    causal_chain: Optional[list[Any]] = None
    recommended_actions: Optional[list[Any]] = None
    engine_version: Optional[str] = None
    explanation: Optional[str] = None
    missing_evidence: Optional[list[Any]] = None
    extra: Optional[dict[str, Any]] = None
    created_at: datetime

    @model_validator(mode="wrap")
    @classmethod
    def _pull_missing_from_extra(cls, data: Any, handler):  # type: ignore[no-untyped-def]
        obj = handler(data)
        if obj.missing_evidence:
            return obj
        extra = obj.extra if isinstance(obj.extra, dict) else None
        if extra is None and hasattr(data, "extra"):
            extra = data.extra if isinstance(data.extra, dict) else None
        if isinstance(extra, dict) and extra.get("missing_evidence") is not None:
            object.__setattr__(obj, "missing_evidence", extra.get("missing_evidence"))
        return obj


class RcaResponse(BaseModel):
    event_id: str
    hypotheses: list[RcaHypothesisOut]
    decision_state: Optional[str] = None
