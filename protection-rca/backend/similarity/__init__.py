"""Historical similarity — classical features; optional vector DB adapter."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class SimilarityResult:
    status: str  # OK | NOT_AVAILABLE
    message: str
    similar_events: list[dict[str, Any]] = field(default_factory=list)
    note: str = "Supporting evidence only — never treat as proof"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SimilarityService:
    """
    Similarity search.

    Without a vector_db adapter → NOT_AVAILABLE.
    With an adapter implementing ``query(embedding=, top_k=)`` → OK results
    that remain supporting evidence only (never proof).
    """

    def __init__(self, vector_db: Any = None) -> None:
        self.vector_db = vector_db

    def find_similar(
        self, *, event_id: str, embedding: Optional[list[float]] = None, top_k: int = 5
    ) -> SimilarityResult:
        if self.vector_db is None:
            return SimilarityResult(
                status="NOT_AVAILABLE",
                message="SIMILARITY RESULT: NOT AVAILABLE",
                similar_events=[],
            )
        try:
            rows = self.vector_db.query(embedding=embedding, top_k=top_k)
            filtered = [r for r in (rows or []) if r.get("event_id") != event_id]
            return SimilarityResult(
                status="OK" if filtered else "NOT_AVAILABLE",
                message=(
                    "Similar events retrieved (supporting evidence only)"
                    if filtered
                    else "SIMILARITY RESULT: NOT AVAILABLE"
                ),
                similar_events=filtered,
            )
        except Exception as exc:  # noqa: BLE001
            return SimilarityResult(
                status="NOT_AVAILABLE",
                message="SIMILARITY RESULT: NOT AVAILABLE",
                similar_events=[],
                note=f"Supporting evidence only — query failed: {exc}",
            )
