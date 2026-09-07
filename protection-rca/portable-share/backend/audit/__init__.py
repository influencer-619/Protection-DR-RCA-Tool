"""Audit service helper for analysis pipeline actions."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Optional
import uuid


@dataclass
class AuditEntry:
    audit_id: str
    action: str
    entity_type: str
    entity_id: str
    user_id: Optional[str]
    timestamp: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AuditService:
    """In-memory audit helper; persist via DB layer when wired."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(
        self,
        *,
        action: str,
        entity_type: str,
        entity_id: str,
        user_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
    ) -> AuditEntry:
        entry = AuditEntry(
            audit_id=f"aud-{uuid.uuid4().hex[:12]}",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            user_id=user_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            details=dict(details or {}),
        )
        self._entries.append(entry)
        return entry

    def list_for(self, entity_id: str) -> list[AuditEntry]:
        return [e for e in self._entries if e.entity_id == entity_id]
