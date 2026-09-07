"""Persist COMTRADE metadata/channels and stream waveform samples."""

from __future__ import annotations

import hashlib
import json
import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import ComtradeChannel, ComtradeFile, Event, EventFile, EventTimeline
from app.services.storage import StorageService

logger = logging.getLogger(__name__)

_MARKER_COLORS = {
    "record_start": "#5b9fd4",
    "trigger": "#d64545",
    "pickup": "#e8a838",
    "trip": "#e85d4c",
    "breaker": "#5fbf7a",
    "fault": "#c77dff",
    "default": "#9aabbd",
}


def _friendly_timeline_label(event_type: str, label: Optional[str] = None) -> str:
    et = (event_type or "").upper()
    raw = (label or "").strip()
    mapping = {
        "PROTECTION_PICKUP": "Pickup",
        "PROTECTION_TRIP": "Trip",
        "BREAKER_TRIP_COMMAND": "Trip command",
        "FAULT_INCEPTION": "Fault inception",
        "CURRENT_INCREASE": "Current increase",
        "CURRENT_INTERRUPTION": "Current interruption",
        "52A_CHANGE": "52a change",
        "52B_CHANGE": "52b change",
        "RECLOSE": "Reclose",
        "LOCKOUT": "Lockout",
        "INTERTRIP": "Intertrip",
    }
    base = mapping.get(et)
    if base and raw and raw.upper() not in (et, base.upper()) and "DIGITAL:" not in raw.upper():
        # Prefer channel / signal name when more specific
        if any(k in raw.upper() for k in ("PICKUP", "TRIP", "52", "ZONE", "OP", "CMD")):
            return raw.replace("digital:", "").strip()
        return f"{base} ({raw})"
    if base:
        return base
    if raw:
        return raw.replace("digital:", "").strip() or et.replace("_", " ").title()
    return et.replace("_", " ").title() or "Event"


def _marker_color_for(event_type: str, label: str) -> str:
    blob = f"{event_type} {label}".upper()
    if "TRIGGER" in blob or "RECORD START" in blob:
        return _MARKER_COLORS["trigger" if "TRIGGER" in blob else "record_start"]
    if "PICKUP" in blob or "START" in blob and "RECORD" not in blob:
        return _MARKER_COLORS["pickup"]
    if "TRIP" in blob or "LOCKOUT" in blob or "INTERTRIP" in blob:
        return _MARKER_COLORS["trip"]
    if "52" in blob or "BREAKER" in blob or "INTERRUPT" in blob:
        return _MARKER_COLORS["breaker"]
    if "FAULT" in blob or "INCEPTION" in blob or "CURRENT_INCREASE" in blob:
        return _MARKER_COLORS["fault"]
    return _MARKER_COLORS["default"]


def _digital_edge_markers(channels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rising-edge markers from digital sample series (works before/without analysis)."""
    out: list[dict[str, Any]] = []
    for c in channels:
        if str(c.get("channel_type") or "").upper() != "DIGITAL":
            continue
        name = str(c.get("name") or "D")
        samples = c.get("samples") or []
        ts = c.get("timestamps_us") or []
        if not samples or not ts or len(ts) != len(samples):
            continue
        prev = None
        for i, v in enumerate(samples):
            try:
                cur = int(float(v))
            except (TypeError, ValueError):
                continue
            if prev is not None and prev <= 0 and cur > 0:
                t_us = float(ts[i])
                out.append(
                    {
                        "t_us": t_us,
                        "label": name,
                        "color": _marker_color_for("", name),
                        "source": "digital_edge",
                    }
                )
                break  # first assert only per channel
            prev = cur
    return out


def _dedupe_markers(markers: list[dict[str, Any]], *, tol_us: float = 2500.0) -> list[dict[str, Any]]:
    """Keep earliest unique labels; drop near-duplicates (Trip vs TRIP_CMD, etc.)."""

    def _norm(lab: str) -> str:
        return "".join(ch for ch in lab.upper() if ch.isalnum())

    markers = sorted(markers, key=lambda m: (float(m.get("t_us") or 0), len(str(m.get("label") or ""))))
    kept: list[dict[str, Any]] = []
    for m in markers:
        t = float(m.get("t_us") or 0)
        lab = str(m.get("label") or "").strip()
        key = _norm(lab)
        if not key:
            continue
        dup_idx = None
        for i, k in enumerate(kept):
            if abs(t - float(k.get("t_us") or 0)) > tol_us:
                continue
            kk = _norm(str(k.get("label") or ""))
            if kk == key or kk in key or key in kk:
                dup_idx = i
                break
        if dup_idx is not None:
            # Prefer shorter label at same/near time
            if len(lab) < len(str(kept[dup_idx].get("label") or "")):
                kept[dup_idx] = m
            continue
        kept.append(m)
    return kept


def _put_json(storage: StorageService, payload: Any, *, prefix: str, suffix: str) -> str:
    raw = json.dumps(payload).encode("utf-8")
    sha = hashlib.sha256(raw).hexdigest()
    return storage.put_bytes(raw, sha256=sha, prefix=prefix, suffix=suffix)


def _materialize_event_files(storage: StorageService, files: list[EventFile]) -> list[Path]:
    """Write COMTRADE-relevant event files to a temp dir for ingest.

    Skips ZIP packages and non-COMTRADE attachments so the original archive
    binary cannot confuse CFG/DAT detection.
    """
    comtrade_exts = {".cfg", ".dat", ".cff", ".hdr", ".inf"}
    tmp = Path(tempfile.mkdtemp(prefix="wf_"))
    paths: list[Path] = []
    for ef in files:
        name = ef.original_filename or f"{ef.sha256}.bin"
        ext = Path(name).suffix.lower()
        if ext not in comtrade_exts:
            continue
        if (ef.source_type or "").upper() == "PACKAGE":
            continue
        raw = storage.get_bytes(ef.storage_key)
        dest = tmp / Path(name).name
        dest.write_bytes(raw)
        paths.append(dest)
    return paths


async def ingest_and_persist_comtrade(
    db: AsyncSession,
    event: Event,
    *,
    storage: Optional[StorageService] = None,
) -> dict[str, Any]:
    """Parse uploaded event files, persist ComtradeFile/Channel, cache samples."""
    storage = storage or StorageService()
    files = (
        await db.execute(select(EventFile).where(EventFile.event_id == event.id))
    ).scalars().all()
    if not files:
        return {"success": False, "error": "No uploaded files", "status": "NOT_AVAILABLE"}

    paths = _materialize_event_files(storage, list(files))
    from comtrade.service import ComtradeService

    svc = ComtradeService()
    ingest = svc.ingest(paths, validate_after_parse=True)
    if not ingest.success or ingest.record is None:
        event.data_quality = "INVALID" if ingest.detection and not ingest.detection.is_comtrade else "POOR"
        return {
            "success": False,
            "error": ingest.error or "parse failed",
            "detection": ingest.detection.to_dict() if ingest.detection else None,
            "validation": ingest.validation.to_dict() if ingest.validation else None,
        }

    record = ingest.record
    det = ingest.detection
    val = ingest.validation

    # Remove prior comtrade rows for re-analyse
    existing = (
        await db.execute(select(ComtradeFile).where(ComtradeFile.event_id == event.id))
    ).scalars().all()
    for row in existing:
        await db.delete(row)
    await db.flush()

    cfg_key = dat_key = None
    for ef in files:
        name = (ef.original_filename or "").lower()
        if name.endswith(".cfg"):
            cfg_key = ef.storage_key
        elif name.endswith(".dat"):
            dat_key = ef.storage_key
        elif name.endswith(".cff"):
            cfg_key = ef.storage_key

    rev = getattr(det, "revision", None)
    revision_year = int(rev) if rev and str(rev).isdigit() else None

    # Prefer CFG start/trigger times from the parsed record
    start_ts = getattr(record, "start_time", None)
    trigger_ts = getattr(record, "trigger_time", None)

    warn_list: list[str] = []
    _skip_warn = "Ambiguous numeric dates are interpreted as dd/mm/yyyy"
    if val is not None:
        for issue in getattr(val, "issues", None) or []:
            sev = str(getattr(issue, "severity", "") or "").lower()
            msg = getattr(issue, "message", None) or str(issue)
            if sev in ("warning", "warn", "info") or "warning" in sev:
                if _skip_warn not in str(msg):
                    warn_list.append(str(msg))
        for w in getattr(val, "warnings", None) or []:
            if _skip_warn not in str(w):
                warn_list.append(str(w))
    if not warn_list and det is not None:
        for n in getattr(det, "notes", None) or []:
            if _skip_warn not in str(n):
                warn_list.append(str(n))

    ct = ComtradeFile(
        event_id=event.id,
        event_file_id=files[0].id,
        station_name=record.station,
        recording_device=record.device,
        revision_year=revision_year,
        start_timestamp=start_ts,
        trigger_timestamp=trigger_ts,
        sample_rate_hz=(
            record.sample_rates[0].sample_rate_hz if record.sample_rates else None
        ),
        total_samples=record.samples,
        analog_channel_count=len(record.analog_channels or []),
        digital_channel_count=len(record.digital_channels or []),
        frequency_hz=record.nominal_frequency,
        line_frequency_hz=record.nominal_frequency,
        cfg_storage_key=cfg_key,
        dat_storage_key=dat_key,
        parser_version=get_settings().comtrade_parser_version,
        validation_status=getattr(val, "status", None) if val else getattr(det, "status", None),
        data_quality=getattr(val, "data_quality", None) if val else None,
        parse_warnings=warn_list or None,
        header_metadata={
            "standard": getattr(det, "standard", None),
            "container": getattr(det, "container", None),
            "data_format": getattr(det, "data_format", None),
            "encoding": getattr(det, "encoding", None),
            "record_id": record.record_id,
            "start_time": start_ts.isoformat() if start_ts else None,
            "trigger_time": trigger_ts.isoformat() if trigger_ts else None,
        },
    )
    db.add(ct)
    await db.flush()

    # Persist sample cache (JSON float lists — engineering values)
    timestamps = list(record.timestamps or [])
    scaled = record.scaled_values or {}
    raw = record.raw_values or {}
    max_points = 20000  # cap for API responsiveness

    def _trim(arr: list[Any]) -> list[Any]:
        if len(arr) <= max_points:
            return list(arr)
        step = max(1, len(arr) // max_points)
        return list(arr[::step])[:max_points]

    def _channel_samples(name: str, *, analog: bool) -> list[Any]:
        if analog:
            series = scaled.get(name) or raw.get(name) or []
        else:
            series = raw.get(name) or scaled.get(name) or []
        return list(series)

    ts_trim = _trim(timestamps)
    ts_key = _put_json(storage, ts_trim, prefix=f"waveforms/{event.id}", suffix=".ts.json")

    for idx, ch in enumerate(record.analog_channels or []):
        name = ch.name if hasattr(ch, "name") else (ch.get("name") if isinstance(ch, dict) else f"A{idx}")
        units = getattr(ch, "unit", None) or getattr(ch, "units", None)
        if isinstance(ch, dict):
            units = ch.get("unit") or ch.get("units")
        phase = ch.phase if hasattr(ch, "phase") else (ch.get("phase") if isinstance(ch, dict) else None)
        samples = _channel_samples(str(name), analog=True)
        samples_trim = _trim(list(samples))
        sample_key = _put_json(
            storage, samples_trim, prefix=f"waveforms/{event.id}", suffix=f".{name}.json"
        )
        db.add(
            ComtradeChannel(
                comtrade_file_id=ct.id,
                channel_index=idx,
                channel_type="ANALOG",
                name=str(name),
                phase=phase,
                units=units,
                channel_metadata={
                    "sample_storage_key": sample_key,
                    "timestamp_storage_key": ts_key,
                    "sample_count": len(samples_trim),
                    "full_sample_count": len(samples),
                    "trimmed": len(samples) > len(samples_trim),
                },
            )
        )

    for idx, ch in enumerate(record.digital_channels or []):
        name = ch.name if hasattr(ch, "name") else (ch.get("name") if isinstance(ch, dict) else f"D{idx}")
        samples = _channel_samples(str(name), analog=False)
        samples_trim = _trim(list(samples))
        sample_key = _put_json(
            storage, samples_trim, prefix=f"waveforms/{event.id}", suffix=f".{name}.json"
        )
        db.add(
            ComtradeChannel(
                comtrade_file_id=ct.id,
                channel_index=idx,
                channel_type="DIGITAL",
                name=str(name),
                channel_metadata={
                    "sample_storage_key": sample_key,
                    "timestamp_storage_key": ts_key,
                    "sample_count": len(samples_trim),
                },
            )
        )

    if val and getattr(val, "data_quality", None):
        event.data_quality = val.data_quality
    elif det:
        event.data_quality = "ACCEPTABLE" if det.status == "SUPPORTED" else "WARNING"
    # Mirror event DQ onto COMTRADE row for the UI badge
    if event.data_quality and not ct.data_quality:
        ct.data_quality = event.data_quality

    await db.flush()
    return {
        "success": True,
        "comtrade_file_id": ct.id,
        "analog": ct.analog_channel_count,
        "digital": ct.digital_channel_count,
        "samples": ct.total_samples,
        "validation": val.to_dict() if val else None,
        "detection": det.to_dict() if det else None,
        "record": record,
    }


async def load_waveform_payload(
    db: AsyncSession,
    event_id: str,
    *,
    storage: Optional[StorageService] = None,
    max_channels: int = 32,
) -> dict[str, Any]:
    storage = storage or StorageService()
    ct = (
        await db.execute(
            select(ComtradeFile)
            .where(ComtradeFile.event_id == event_id)
            .order_by(ComtradeFile.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if ct is None:
        # Attempt on-demand ingest
        event = (
            await db.execute(select(Event).where(Event.id == event_id))
        ).scalar_one_or_none()
        if event is None:
            return {"event_id": event_id, "channels": [], "note": "Event not found"}
        result = await ingest_and_persist_comtrade(db, event, storage=storage)
        if not result.get("success"):
            return {
                "event_id": event_id,
                "channels": [],
                "note": result.get("error") or "No parsed COMTRADE channels yet; upload and analyse first.",
            }
        ct = (
            await db.execute(
                select(ComtradeFile)
                .where(ComtradeFile.event_id == event_id)
                .order_by(ComtradeFile.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()

    if ct is None:
        return {"event_id": event_id, "channels": [], "note": "COMTRADE metadata missing"}

    channels = (
        await db.execute(
            select(ComtradeChannel)
            .where(ComtradeChannel.comtrade_file_id == ct.id)
            .order_by(ComtradeChannel.channel_type, ComtradeChannel.channel_index)
            .limit(max_channels)
        )
    ).scalars().all()

    out = []
    markers = []
    for c in channels:
        meta = c.channel_metadata or {}
        samples = None
        timestamps_us = None
        sk = meta.get("sample_storage_key")
        tk = meta.get("timestamp_storage_key")
        if sk:
            try:
                samples = json.loads(storage.get_bytes(sk).decode("utf-8"))
            except Exception as exc:  # noqa: BLE001
                logger.warning("sample load failed %s: %s", sk, exc)
        if tk:
            try:
                timestamps_us = json.loads(storage.get_bytes(tk).decode("utf-8"))
            except Exception:  # noqa: BLE001
                timestamps_us = None
        if samples and (not timestamps_us or len(timestamps_us) != len(samples)):
            fs = float(ct.sample_rate_hz or 0) or None
            dt_us = (1e6 / fs) if fs and fs > 0 else 1.0
            timestamps_us = [i * dt_us for i in range(len(samples))]
        out.append(
            {
                "name": c.name,
                "channel_type": c.channel_type,
                "phase": c.phase,
                "units": c.units,
                "sample_count": meta.get("sample_count") or (len(samples) if samples else None),
                "samples": samples,
                "timestamps_us": timestamps_us,
            }
        )

    markers: list[dict[str, Any]] = []
    # Always anchor at t=0 when we have waveform data
    if any((c.get("samples") or []) for c in out):
        markers.append(
            {"t_us": 0.0, "label": "Record start", "color": _MARKER_COLORS["record_start"]}
        )

    try:
        if ct.start_timestamp and ct.trigger_timestamp:
            delta = (ct.trigger_timestamp - ct.start_timestamp).total_seconds() * 1e6
            if delta > 1.0:  # > 1 µs — CFG pre-trigger / trigger offset
                markers.append(
                    {
                        "t_us": float(delta),
                        "label": "Trigger",
                        "color": _MARKER_COLORS["trigger"],
                    }
                )
    except Exception:  # noqa: BLE001
        pass

    # Timeline events from analysis (pickup / trip / breaker / inception)
    timeline_rows = (
        await db.execute(
            select(EventTimeline)
            .where(EventTimeline.event_id == event_id)
            .order_by(EventTimeline.sequence.asc())
            .limit(80)
        )
    ).scalars().all()
    timeline_rows = sorted(
        timeline_rows,
        key=lambda r: (r.t_us is None, float(r.t_us) if r.t_us is not None else 0.0, r.sequence or 0),
    )
    has_cfg_trigger = any(str(m.get("label")) == "Trigger" for m in markers)
    for row in timeline_rows:
        if row.t_us is None:
            continue
        t_us = float(row.t_us)
        if t_us < 0:
            continue
        label = _friendly_timeline_label(str(row.event_type or ""), str(row.label or "") or None)
        markers.append(
            {
                "t_us": t_us,
                "label": label,
                "color": _marker_color_for(str(row.event_type or ""), label),
                "source": "timeline",
            }
        )
        et = str(row.event_type or "").upper()
        # When CFG start==trigger, place Trigger at first trip / inception
        if not has_cfg_trigger and et in (
            "PROTECTION_TRIP",
            "BREAKER_TRIP_COMMAND",
            "FAULT_INCEPTION",
        ):
            markers.append(
                {
                    "t_us": t_us,
                    "label": "Trigger",
                    "color": _MARKER_COLORS["trigger"],
                    "source": "timeline_trigger",
                }
            )
            has_cfg_trigger = True

    # Digital rising edges from cached samples (visible even before analysis)
    edge_markers = _digital_edge_markers(out)
    if not has_cfg_trigger:
        for em in edge_markers:
            lab = str(em.get("label") or "").upper()
            if any(k in lab for k in ("TRIP", "TRIGGER", "CMD")):
                markers.append(
                    {
                        "t_us": float(em["t_us"]),
                        "label": "Trigger",
                        "color": _MARKER_COLORS["trigger"],
                        "source": "digital_trigger",
                    }
                )
                has_cfg_trigger = True
                break
    markers.extend(edge_markers)

    markers = _dedupe_markers(markers)
    # Cap list for UI clarity
    if len(markers) > 40:
        markers = markers[:40]

    return {
        "event_id": event_id,
        "channels": out,
        "markers": markers,
        "note": None if any((c.get("samples") or []) for c in out) else "Channels present but samples not cached",
        "comtrade_file_id": ct.id,
        "validation_status": ct.validation_status,
        "data_quality": ct.data_quality,
    }
