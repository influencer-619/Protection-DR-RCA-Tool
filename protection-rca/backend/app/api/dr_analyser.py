"""DR analyser Phase A/B/C API — channel map, multi-end, settings ingest, folder watch."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import User
from app.services import event_service

router = APIRouter(prefix="/api/dr", tags=["dr-analyser"])

_VALID_ROLES = frozenset(
    {"IA", "IB", "IC", "IN", "VA", "VB", "VC", "VN", "I", "V", "UNKNOWN"}
)


class ChannelMapBody(BaseModel):
    channel_map: dict[str, str] = Field(default_factory=dict)


class DigitalMapBody(BaseModel):
    digital_map: dict[str, Any] = Field(default_factory=dict)


class EndLabelBody(BaseModel):
    event_file_id: str
    end_label: str = "LOCAL"


class MultiEndBody(BaseModel):
    local_comtrade_file_id: Optional[str] = None
    remote_comtrade_file_id: Optional[str] = None
    sync_offset_us: Optional[float] = None


class WatchScanBody(BaseModel):
    folder: Optional[str] = None


@router.get("/events/{event_id}/channel-map")
async def get_channel_map(event_id: str, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    extra = event.extra if isinstance(event.extra, dict) else {}
    channel_map = extra.get("channel_map") if isinstance(extra.get("channel_map"), dict) else {}
    inferred = {}
    ra = extra.get("report_analysis") if isinstance(extra.get("report_analysis"), dict) else {}
    ea = ra.get("electrical_analysis") if isinstance(ra.get("electrical_analysis"), dict) else {}
    if isinstance(ea.get("channel_roles"), dict):
        inferred = ea["channel_roles"]
    # Also list COMTRADE channel names for the UI
    from sqlalchemy import select
    from app.models import ComtradeChannel, ComtradeFile

    ct = (
        await db.execute(
            select(ComtradeFile)
            .where(ComtradeFile.event_id == event_id)
            .order_by(ComtradeFile.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    channels = []
    if ct:
        rows = (
            await db.execute(
                select(ComtradeChannel)
                .where(ComtradeChannel.comtrade_file_id == ct.id)
                .order_by(ComtradeChannel.channel_index)
            )
        ).scalars().all()
        for c in rows:
            if c.channel_type != "ANALOG":
                continue
            channels.append(
                {
                    "name": c.name,
                    "phase": c.phase,
                    "units": c.units,
                    "mapped_signal": c.mapped_signal,
                    "inferred": inferred.get(c.name),
                    "assigned": channel_map.get(c.name),
                }
            )
    return {
        "event_id": event_id,
        "channel_map": channel_map,
        "inferred_roles": inferred,
        "channels": channels,
        "valid_roles": sorted(_VALID_ROLES),
    }


@router.put("/events/{event_id}/channel-map")
async def put_channel_map(
    event_id: str,
    body: ChannelMapBody,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    cleaned = {
        str(k): str(v).upper().strip()
        for k, v in (body.channel_map or {}).items()
        if k and str(v).upper().strip() in _VALID_ROLES
    }
    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    extra["channel_map"] = cleaned
    event.extra = extra

    # Mirror onto ComtradeChannel.mapped_signal when possible
    from sqlalchemy import select
    from app.models import ComtradeChannel, ComtradeFile

    ct = (
        await db.execute(
            select(ComtradeFile)
            .where(ComtradeFile.event_id == event_id)
            .order_by(ComtradeFile.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if ct:
        rows = (
            await db.execute(
                select(ComtradeChannel).where(ComtradeChannel.comtrade_file_id == ct.id)
            )
        ).scalars().all()
        for c in rows:
            if c.name in cleaned:
                c.mapped_signal = cleaned[c.name]

    await db.commit()
    return {"event_id": event_id, "channel_map": cleaned, "saved": True}


@router.get("/events/{event_id}/digital-map")
async def get_digital_map(event_id: str, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    """Protection digitals ↔ DR targets (pickup / trip / 52a / …)."""
    from protection.digital_targets import (
        VALID_TARGET_ROLES,
        infer_element_code,
        infer_target_role,
        normalize_digital_map,
    )

    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    extra = event.extra if isinstance(event.extra, dict) else {}
    digital_map = normalize_digital_map(
        extra.get("digital_map") if isinstance(extra.get("digital_map"), dict) else {}
    )

    from sqlalchemy import select
    from app.models import ComtradeChannel, ComtradeFile

    ct = (
        await db.execute(
            select(ComtradeFile)
            .where(ComtradeFile.event_id == event_id)
            .order_by(ComtradeFile.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    channels: list[dict[str, Any]] = []
    if ct:
        rows = (
            await db.execute(
                select(ComtradeChannel)
                .where(ComtradeChannel.comtrade_file_id == ct.id)
                .order_by(ComtradeChannel.channel_index)
            )
        ).scalars().all()
        for c in rows:
            if c.channel_type != "DIGITAL":
                continue
            inferred_role = infer_target_role(c.name)
            inferred_el = infer_element_code(c.name)
            assigned = digital_map.get(c.name) or {}
            channels.append(
                {
                    "name": c.name,
                    "phase": c.phase,
                    "inferred_role": inferred_role,
                    "inferred_element": inferred_el,
                    "assigned_role": assigned.get("role"),
                    "assigned_element": assigned.get("element") or None,
                }
            )
    return {
        "event_id": event_id,
        "digital_map": digital_map,
        "channels": channels,
        "valid_roles": sorted(VALID_TARGET_ROLES),
        "valid_elements": [
            "21",
            "50",
            "50BF",
            "50N",
            "51",
            "51N",
            "67",
            "67N",
            "79",
            "86",
            "87B",
            "87L",
            "87T",
            "87G",
            "",
        ],
    }


@router.put("/events/{event_id}/digital-map")
async def put_digital_map(
    event_id: str,
    body: DigitalMapBody,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    from protection.digital_targets import normalize_digital_map

    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    cleaned = normalize_digital_map(body.digital_map)
    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    extra["digital_map"] = cleaned
    event.extra = extra

    # Mirror role onto ComtradeChannel.mapped_signal as ROLE|ELEMENT when set
    from sqlalchemy import select
    from app.models import ComtradeChannel, ComtradeFile

    ct = (
        await db.execute(
            select(ComtradeFile)
            .where(ComtradeFile.event_id == event_id)
            .order_by(ComtradeFile.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if ct:
        rows = (
            await db.execute(
                select(ComtradeChannel).where(ComtradeChannel.comtrade_file_id == ct.id)
            )
        ).scalars().all()
        for c in rows:
            if c.channel_type != "DIGITAL":
                continue
            if c.name in cleaned:
                entry = cleaned[c.name]
                role = entry.get("role") or "UNKNOWN"
                el = entry.get("element") or ""
                c.mapped_signal = f"{role}|{el}" if el else role

    await db.commit()
    return {"event_id": event_id, "digital_map": cleaned, "saved": True}


@router.get("/events/{event_id}/comtrade-ends")
async def get_comtrade_ends(event_id: str, db: DbSession, user: CurrentUser) -> dict[str, Any]:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    from app.services.multi_comtrade import list_comtrade_ends, pair_local_remote, sync_offset_us
    from datetime import datetime

    ends = await list_comtrade_ends(db, event_id)
    local, remote = pair_local_remote(ends)
    offset = None
    if local and remote:
        def _parse(ts: Optional[str]):
            if not ts:
                return None
            try:
                return datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                return None

        offset = sync_offset_us(_parse(local.get("trigger_timestamp")), _parse(remote.get("trigger_timestamp")))
    extra = event.extra if isinstance(event.extra, dict) else {}
    return {
        "event_id": event_id,
        "ends": ends,
        "local": local,
        "remote": remote,
        "computed_sync_offset_us": offset,
        "multi_end": extra.get("multi_end") or {},
    }


@router.post("/events/{event_id}/end-label")
async def post_end_label(
    event_id: str,
    body: EndLabelBody,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    from app.services.multi_comtrade import set_file_end_label

    try:
        return await set_file_end_label(db, event_id, body.event_file_id, body.end_label)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.put("/events/{event_id}/multi-end")
async def put_multi_end(
    event_id: str,
    body: MultiEndBody,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    from app.services.multi_comtrade import store_multi_end_config

    cfg = await store_multi_end_config(
        db,
        event,
        local_file_id=body.local_comtrade_file_id,
        remote_file_id=body.remote_comtrade_file_id,
        sync_offset_us_value=body.sync_offset_us,
    )
    return {"event_id": event_id, "multi_end": cfg}


@router.post("/events/{event_id}/settings-ingest")
async def post_settings_ingest(
    event_id: str,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    from app.services.settings_ingest import ingest_settings_bytes, merge_ingested_into_event_extra

    raw = await file.read()
    ingested = ingest_settings_bytes(raw, filename=file.filename or "settings.txt")
    if ingested.get("status") != "OK":
        return {"event_id": event_id, **ingested, "merged": False}
    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    event.extra = merge_ingested_into_event_extra(extra, ingested)
    await db.commit()
    return {
        "event_id": event_id,
        "vendor": ingested.get("vendor"),
        "param_count": ingested.get("param_count"),
        "mapped": ingested.get("mapped"),
        "merged": True,
    }


@router.get("/watch/scan")
async def watch_scan(
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
    folder: Optional[str] = Query(None),
) -> dict[str, Any]:
    from app.services.folder_watch import poll_once

    _ = db  # reserved for future seen-hash persistence
    return poll_once(folder)


@router.post("/watch/scan")
async def watch_scan_post(
    body: WatchScanBody,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    from app.services.folder_watch import poll_once

    _ = db
    return poll_once(body.folder)
