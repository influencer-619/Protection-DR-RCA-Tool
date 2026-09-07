"""Classical historical similarity (supporting evidence only).

Uses scikit-learn cosine similarity on deterministic event feature vectors.
Optional pgvector adapter can be injected; without it, an in-process /
JSONB feature store is used (works on SQLite and Postgres).
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, FaultClassification, SimilarEvent
from similarity import SimilarityResult, SimilarityService

logger = logging.getLogger(__name__)

# Module-level feature cache for classical similarity (process-local).
_FEATURE_STORE: dict[str, list[float]] = {}


def build_event_embedding(event: Event, fault_type: Optional[str] = None) -> list[float]:
    """Deterministic low-dim feature vector — never invents measurements."""
    dq_map = {
        "GOOD": 1.0,
        "ACCEPTABLE": 0.8,
        "WARNING": 0.5,
        "POOR": 0.25,
        "INVALID": 0.0,
    }
    ft_hash = float(sum(ord(c) for c in (fault_type or "UNKNOWN")[:8]) % 97) / 97.0
    status_hash = float(sum(ord(c) for c in (event.status or "")[:8]) % 53) / 53.0
    decision_hash = float(sum(ord(c) for c in (event.decision_state or "")[:8]) % 59) / 59.0
    v_kv = float(event.nominal_voltage_kv or 0.0) / 400.0
    f_hz = float(event.nominal_frequency_hz or 50.0) / 60.0
    dq = dq_map.get((event.data_quality or "").upper(), 0.4)
    return [v_kv, f_hz, dq, ft_hash, status_hash, decision_hash]


class JsonFeatureIndex:
    """In-process cosine index; optional bridge to pgvector later."""

    def __init__(self) -> None:
        self._store = _FEATURE_STORE

    def upsert(self, event_id: str, embedding: list[float]) -> None:
        self._store[event_id] = list(embedding)

    def query(
        self, *, embedding: Optional[list[float]] = None, top_k: int = 5
    ) -> list[dict[str, Any]]:
        if not embedding or not self._store:
            return []
        q = np.asarray(embedding, dtype=float)
        qn = np.linalg.norm(q) or 1.0
        scored: list[tuple[str, float]] = []
        for eid, vec in self._store.items():
            v = np.asarray(vec, dtype=float)
            if v.shape != q.shape:
                continue
            sim = float(np.dot(q, v) / ((np.linalg.norm(v) or 1.0) * qn))
            scored.append((eid, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return [
            {
                "event_id": eid,
                "similarity": round(score, 4),
                "note": "Supporting evidence only — never treat as proof",
            }
            for eid, score in scored[:top_k]
            if score > 0.01
        ]


def get_similarity_service() -> SimilarityService:
    return SimilarityService(vector_db=JsonFeatureIndex())


async def index_and_link_similar(db: AsyncSession, event: Event, top_k: int = 5) -> SimilarityResult:
    fault = (
        await db.execute(
            select(FaultClassification)
            .where(FaultClassification.event_id == event.id, FaultClassification.is_primary.is_(True))
            .limit(1)
        )
    ).scalar_one_or_none()
    emb = build_event_embedding(event, fault.fault_type if fault else None)
    index = JsonFeatureIndex()
    # Seed index from DB extras if present
    others = (
        await db.execute(select(Event).where(Event.id != event.id).limit(200))
    ).scalars().all()
    for o in others:
        extra = o.extra if isinstance(o.extra, dict) else {}
        stored = extra.get("similarity_embedding")
        if stored:
            index.upsert(o.id, list(stored))
        else:
            index.upsert(o.id, build_event_embedding(o))

    index.upsert(event.id, emb)
    extra = dict(event.extra or {}) if isinstance(event.extra, dict) else {}
    extra["similarity_embedding"] = emb
    event.extra = extra

    svc = SimilarityService(vector_db=index)
    result = svc.find_similar(event_id=event.id, embedding=emb, top_k=top_k + 1)
    # Persist links excluding self
    for row in result.similar_events:
        sid = row.get("event_id")
        if not sid or sid == event.id:
            continue
        exists = (
            await db.execute(
                select(SimilarEvent).where(
                    SimilarEvent.event_id == event.id,
                    SimilarEvent.similar_event_id == sid,
                )
            )
        ).scalar_one_or_none()
        if exists:
            exists.similarity_score = float(row.get("similarity") or 0)
            exists.method = "cosine_classical_v1"
            exists.notes = "Supporting evidence only — never treat as proof"
            exists.matched_features = {"embedding_dims": len(emb)}
        else:
            db.add(
                SimilarEvent(
                    event_id=event.id,
                    similar_event_id=sid,
                    similarity_score=float(row.get("similarity") or 0),
                    method="cosine_classical_v1",
                    matched_features={"embedding_dims": len(emb)},
                    notes="Supporting evidence only — never treat as proof",
                )
            )
    await db.flush()
    return result
