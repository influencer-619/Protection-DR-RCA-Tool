"""Multi-COMTRADE helpers: end tagging, clock alignment, remote electrical."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ComtradeFile, Event, EventFile


def sync_offset_us(
    local_trigger: Optional[datetime],
    remote_trigger: Optional[datetime],
) -> Optional[float]:
    """Clock offset = remote_trigger − local_trigger in microseconds."""
    if local_trigger is None or remote_trigger is None:
        return None
    try:
        lt = local_trigger if local_trigger.tzinfo else local_trigger.replace(tzinfo=timezone.utc)
        rt = remote_trigger if remote_trigger.tzinfo else remote_trigger.replace(tzinfo=timezone.utc)
        return (rt - lt).total_seconds() * 1e6
    except Exception:  # noqa: BLE001
        return None


async def list_comtrade_ends(db: AsyncSession, event_id: str) -> list[dict[str, Any]]:
    """List parsed COMTRADE records with optional end labels from file_metadata / header."""
    rows = (
        await db.execute(
            select(ComtradeFile)
            .where(ComtradeFile.event_id == event_id)
            .order_by(ComtradeFile.created_at.asc())
        )
    ).scalars().all()

    ends: list[dict[str, Any]] = []
    for ct in rows:
        end_label = None
        hdr = ct.header_metadata if isinstance(ct.header_metadata, dict) else {}
        end_label = hdr.get("end_label") or hdr.get("terminal") or hdr.get("end")
        if not end_label and ct.event_file_id:
            ef = (
                await db.execute(select(EventFile).where(EventFile.id == ct.event_file_id))
            ).scalar_one_or_none()
            meta = (ef.file_metadata if ef and isinstance(ef.file_metadata, dict) else {}) or {}
            end_label = meta.get("end_label") or meta.get("terminal") or meta.get("end")
        ends.append(
            {
                "comtrade_file_id": ct.id,
                "station_name": ct.station_name,
                "recording_device": ct.recording_device,
                "start_timestamp": ct.start_timestamp.isoformat() if ct.start_timestamp else None,
                "trigger_timestamp": (
                    ct.trigger_timestamp.isoformat() if ct.trigger_timestamp else None
                ),
                "sample_rate_hz": ct.sample_rate_hz,
                "end_label": end_label or ("LOCAL" if not ends else f"REMOTE_{len(ends)}"),
                "analog_channel_count": ct.analog_channel_count,
                "digital_channel_count": ct.digital_channel_count,
            }
        )
    return ends


async def set_file_end_label(
    db: AsyncSession,
    event_id: str,
    event_file_id: str,
    end_label: str,
) -> dict[str, Any]:
    """Tag an uploaded EventFile as LOCAL / REMOTE / custom for multi-ended analysis."""
    ef = (
        await db.execute(
            select(EventFile).where(
                EventFile.id == event_file_id,
                EventFile.event_id == event_id,
            )
        )
    ).scalar_one_or_none()
    if ef is None:
        raise ValueError("Event file not found")
    meta = dict(ef.file_metadata) if isinstance(ef.file_metadata, dict) else {}
    meta["end_label"] = str(end_label).strip().upper() or "LOCAL"
    ef.file_metadata = meta

    # Mirror onto linked ComtradeFile header_metadata when present
    cts = (
        await db.execute(select(ComtradeFile).where(ComtradeFile.event_file_id == ef.id))
    ).scalars().all()
    for ct in cts:
        hdr = dict(ct.header_metadata) if isinstance(ct.header_metadata, dict) else {}
        hdr["end_label"] = meta["end_label"]
        ct.header_metadata = hdr

    await db.commit()
    return {"event_file_id": ef.id, "end_label": meta["end_label"]}


def pair_local_remote(ends: list[dict[str, Any]]) -> tuple[Optional[dict], Optional[dict]]:
    local = next((e for e in ends if str(e.get("end_label", "")).upper() in ("LOCAL", "L", "A")), None)
    remote = next(
        (
            e
            for e in ends
            if str(e.get("end_label", "")).upper() in ("REMOTE", "R", "B", "REMOTE_1")
            or str(e.get("end_label", "")).upper().startswith("REMOTE")
        ),
        None,
    )
    if local is None and ends:
        local = ends[0]
    if remote is None and len(ends) > 1:
        remote = ends[1] if ends[1] is not local else (ends[0] if local is not ends[0] else None)
    return local, remote


async def store_multi_end_config(
    db: AsyncSession,
    event: Event,
    *,
    local_file_id: Optional[str] = None,
    remote_file_id: Optional[str] = None,
    sync_offset_us_value: Optional[float] = None,
) -> dict[str, Any]:
    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    cfg = dict(extra.get("multi_end") or {})
    if local_file_id:
        cfg["local_comtrade_file_id"] = local_file_id
    if remote_file_id:
        cfg["remote_comtrade_file_id"] = remote_file_id
    if sync_offset_us_value is not None:
        cfg["sync_offset_us"] = float(sync_offset_us_value)
    extra["multi_end"] = cfg
    event.extra = extra
    await db.commit()
    return cfg
