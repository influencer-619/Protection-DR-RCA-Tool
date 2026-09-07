"""Immutable file upload service — SHA-256, extension/size validation, ZIP expand."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Event, EventFile
from app.services.audit_service import write_audit
from app.services.storage import get_storage


SOURCE_BY_EXT = {
    ".cfg": "COMTRADE",
    ".dat": "COMTRADE",
    ".cff": "COMTRADE",
    ".hdr": "COMTRADE",
    ".inf": "COMTRADE",
    ".csv": "SOE",
    ".xml": "SETTINGS",
    ".json": "OTHER",
    ".txt": "RELAY_EVENT_REPORT",
    ".pdf": "ATTACHMENT",
    ".zip": "PACKAGE",
}


def infer_source_type(filename: str, ext: str = "", override: Optional[str] = None) -> str:
    """Classify upload by basename + extension.

    Settings filenames (e.g. relay_base_settings.txt, relay_settings.json) must
    never fall through to RELAY_EVENT_REPORT / OTHER.
    """
    if override:
        return override

    base = Path(filename or "").name
    name = base.lower()
    ext = (ext or Path(name).suffix).lower()

    # --- Settings package (highest priority for name matches) ---
    settings_name = any(
        h in name
        for h in (
            "setting",
            "settings",
            "setpoint",
            "param",
            "relay_set",
            "protection_setting",
        )
    )
    if settings_name or ext == ".set":
        if ext in (".json", ".txt", ".xml", ".csv", ".set"):
            return "SETTINGS"
        # Rare: settings dump with .cfg suffix (not COMTRADE)
        if ext == ".cfg" and ("setting" in name or "settings" in name):
            return "SETTINGS"

    # --- Explicit relay event report ---
    if ext == ".txt" and any(
        h in name for h in ("event_report", "event-report", "relay_event", "ser_report")
    ):
        return "RELAY_EVENT_REPORT"

    # --- Docs / notes ---
    if ext == ".txt" and any(
        h in name for h in ("readme", "upload_order", "license", "changelog", "notes")
    ):
        return "ATTACHMENT"

    # JSON named like a relay package without "setting" — keep OTHER unless event-like
    if ext == ".json" and "relay" in name:
        return "OTHER"

    return SOURCE_BY_EXT.get(ext, "OTHER")


def corrected_source_type(filename: str, stored: Optional[str] = None) -> str:
    """Re-infer source for display / repair of older uploads."""
    inferred = infer_source_type(filename)
    if not stored:
        return inferred
    stored_u = stored.upper()
    # Filename clearly says settings — never keep RELAY_EVENT_REPORT / OTHER
    if inferred == "SETTINGS":
        return "SETTINGS"
    if inferred == "ATTACHMENT" and stored_u in ("RELAY_EVENT_REPORT", "OTHER"):
        return "ATTACHMENT"
    # Extension-specific types should win over crude .txt/.json defaults
    if stored_u in ("RELAY_EVENT_REPORT", "OTHER") and inferred not in (
        "RELAY_EVENT_REPORT",
        "OTHER",
    ):
        return inferred
    return stored

# Safety limits for ZIP expansion (zip-bomb / path traversal protection)
MAX_ZIP_MEMBERS = 200
MAX_ZIP_DEPTH = 3
MAX_ZIP_UNCOMPRESSED_RATIO = 100  # uncompressed/compressed size cap


def _validate_extension(filename: str) -> str:
    settings = get_settings()
    ext = Path(filename).suffix.lower()
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Extension {ext or '(none)'} not allowed",
        )
    return ext


def _safe_member_parts(raw_name: str) -> Optional[list[str]]:
    """Return path parts for a ZIP member; reject traversal / junk."""
    name = (raw_name or "").replace("\\", "/").strip()
    if not name or name.endswith("/"):
        return None
    parts = [p for p in name.split("/") if p and p != "."]
    if not parts or any(p == ".." for p in parts):
        return None
    if parts[0].upper() == "__MACOSX":
        return None
    base = parts[-1]
    if base.lower() in {".ds_store", "thumbs.db", "desktop.ini"}:
        return None
    return parts


def _unique_member_name(parts: list[str], used: set[str]) -> str:
    """Prefer basename so CFG/DAT pairing stays intact; disambiguate collisions."""
    base = parts[-1]
    if base not in used:
        used.add(base)
        return base
    candidate = "__".join(parts)
    if candidate not in used:
        used.add(candidate)
        return candidate
    stem = Path(base).stem
    suf = Path(base).suffix
    n = 2
    while True:
        alt = f"{stem}_{n}{suf}"
        if alt not in used:
            used.add(alt)
            return alt
        n += 1


def expand_zip_bytes(
    data: bytes,
    *,
    depth: int = 0,
    max_depth: int = MAX_ZIP_DEPTH,
    max_members: int = MAX_ZIP_MEMBERS,
    max_total_bytes: Optional[int] = None,
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """
    Expand a ZIP archive into (filename, bytes) members.

    Nested ZIPs are expanded up to max_depth.
    Returns (members, skip_notes).
    """
    settings = get_settings()
    budget = max_total_bytes if max_total_bytes is not None else settings.max_upload_bytes
    allowed = set(settings.allowed_extensions)
    members: list[tuple[str, bytes]] = []
    skipped: list[str] = []
    used_names: set[str] = set()

    if depth > max_depth:
        skipped.append(f"ZIP nesting deeper than {max_depth} levels skipped")
        return members, skipped

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ZIP archive: {exc}",
        ) from exc

    # Zip-bomb guard: total uncompressed size declared in headers
    declared = sum(info.file_size for info in zf.infolist() if not info.is_dir())
    if declared > budget:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"ZIP uncompressed size {declared} bytes exceeds "
                f"{settings.max_upload_size_mb} MB limit"
            ),
        )
    if data and declared / max(len(data), 1) > MAX_ZIP_UNCOMPRESSED_RATIO:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="ZIP compression ratio too high (possible zip bomb)",
        )

    total_out = 0
    with zf:
        infos = [i for i in zf.infolist() if not i.is_dir()]
        if len(infos) > max_members:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ZIP contains more than {max_members} files",
            )
        for info in infos:
            parts = _safe_member_parts(info.filename)
            if parts is None:
                skipped.append(f"Skipped unsafe path: {info.filename}")
                continue
            try:
                raw = zf.read(info)
            except Exception as exc:  # noqa: BLE001
                skipped.append(f"Failed to read {info.filename}: {exc}")
                continue
            total_out += len(raw)
            if total_out > budget:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Extracted ZIP contents exceed upload size limit",
                )

            ext = Path(parts[-1]).suffix.lower()
            if ext == ".zip":
                nested, nest_skip = expand_zip_bytes(
                    raw,
                    depth=depth + 1,
                    max_depth=max_depth,
                    max_members=max_members,
                    max_total_bytes=budget - total_out,
                )
                for n_name, n_data in nested:
                    if n_name in used_names:
                        out_name = _unique_member_name([n_name], used_names)
                    else:
                        used_names.add(n_name)
                        out_name = n_name
                    members.append((out_name, n_data))
                skipped.extend(nest_skip)
                continue

            if ext not in allowed or ext == ".zip":
                skipped.append(f"Skipped unsupported extension: {parts[-1]}")
                continue

            out_name = _unique_member_name(parts, used_names)
            members.append((out_name, raw))

    return members, skipped


async def _store_bytes(
    db: AsyncSession,
    event: Event,
    *,
    filename: str,
    data: bytes,
    content_type: Optional[str],
    source_type: Optional[str],
    uploaded_by: Optional[str],
    request_id: Optional[str],
    file_metadata: Optional[dict] = None,
) -> EventFile:
    settings = get_settings()
    ext = _validate_extension(filename)
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
        )

    sha256 = hashlib.sha256(data).hexdigest()
    existing = await db.execute(
        select(EventFile).where(
            EventFile.event_id == event.id, EventFile.sha256 == sha256
        )
    )
    dup = existing.scalar_one_or_none()
    if dup is not None:
        return dup

    storage = get_storage()
    key = storage.put_bytes(
        data,
        sha256=sha256,
        prefix=f"events/{event.id}",
        suffix=ext,
        content_type=content_type,
    )

    meta = {"extension": ext}
    if file_metadata:
        meta.update(file_metadata)

    ef = EventFile(
        event_id=event.id,
        sha256=sha256,
        file_size=len(data),
        original_filename=filename,
        source_type=infer_source_type(filename, ext, source_type),
        content_type=content_type,
        storage_key=key,
        immutable=True,
        uploaded_by=uploaded_by,
        file_metadata=meta,
    )
    db.add(ef)
    await db.flush()
    await write_audit(
        db,
        action="UPLOAD",
        user_id=uploaded_by,
        object_type="EventFile",
        object_id=ef.id,
        new_value={"sha256": sha256, "filename": filename, "size": len(data)},
        request_id=request_id,
    )
    return ef


async def store_event_file(
    db: AsyncSession,
    event: Event,
    upload: UploadFile,
    *,
    source_type: Optional[str] = None,
    uploaded_by: Optional[str] = None,
    request_id: Optional[str] = None,
) -> list[EventFile]:
    """
    Store an uploaded file. ZIP archives are expanded; each allowed member
    is stored and processed like a direct upload. The original ZIP is kept
    as a PACKAGE attachment for evidence.
    """
    settings = get_settings()
    filename = upload.filename or "upload.bin"
    ext = _validate_extension(filename)

    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > settings.max_upload_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
            )
        chunks.append(chunk)
    data = b"".join(chunks)

    if ext != ".zip":
        ef = await _store_bytes(
            db,
            event,
            filename=filename,
            data=data,
            content_type=upload.content_type,
            source_type=source_type,
            uploaded_by=uploaded_by,
            request_id=request_id,
        )
        return [ef]

    members, skipped = expand_zip_bytes(data)
    if not members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "ZIP contained no allowed files to process. "
                + ("; ".join(skipped[:5]) if skipped else "Archive empty.")
            ),
        )

    stored: list[EventFile] = []
    package = await _store_bytes(
        db,
        event,
        filename=filename,
        data=data,
        content_type=upload.content_type or "application/zip",
        source_type=source_type or "PACKAGE",
        uploaded_by=uploaded_by,
        request_id=request_id,
        file_metadata={
            "extracted": True,
            "member_count": len(members),
            "skipped": skipped[:50],
        },
    )
    stored.append(package)

    for member_name, member_data in members:
        ef = await _store_bytes(
            db,
            event,
            filename=member_name,
            data=member_data,
            content_type=None,
            source_type=infer_source_type(
                member_name, Path(member_name).suffix.lower()
            ),
            uploaded_by=uploaded_by,
            request_id=request_id,
            file_metadata={
                "extracted_from": filename,
                "package_sha256": package.sha256,
            },
        )
        stored.append(ef)

    return stored
