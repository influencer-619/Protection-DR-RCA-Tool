"""Pydantic v2 schemas — uploaded files."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class EventFileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_id: str
    sha256: str
    file_size: int
    original_filename: str
    source_type: str
    content_type: Optional[str] = None
    storage_key: str
    upload_timestamp: datetime
    immutable: bool = True
    uploaded_by: Optional[str] = None
    file_metadata: Optional[dict[str, Any]] = None
    created_at: datetime


class FileUploadResponse(BaseModel):
    file: EventFileOut
    message: str = "File stored immutably"
