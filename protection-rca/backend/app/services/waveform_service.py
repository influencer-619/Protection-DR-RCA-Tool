"""Persist COMTRADE metadata/channels and stream waveform samples."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import tempfile
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import ComtradeChannel, ComtradeFile, Event, EventFile, EventTimeline
from app.services.storage import StorageService

logger = logging.getLogger(__name__)


def _safe_channel_token(name: Any) -> str:
    """Filesystem-safe token for waveform sample keys (keeps DB channel name intact)."""
    token = re.sub(r"[^A-Za-z0-9._+-]+", "_", str(name or "")).strip("._")
    return (token[:80] or "ch")

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


def _file_end_label(ef: EventFile) -> str:
    meta = ef.file_metadata if isinstance(ef.file_metadata, dict) else {}
    return str(meta.get("cascade_role") or meta.get("end_label") or "").strip().upper()


def _group_files_by_end(files: list[EventFile]) -> list[tuple[str, list[EventFile]]]:
    """Group uploaded files by INITIATOR/BACKUP or LOCAL/REMOTE for dual-end ingest.

    Combined Cascade / Local-Remote packages must be ingested separately — mixing two
    CFG/DAT pairs in one parse often fails or keeps only one end.
    """
    buckets: dict[str, list[EventFile]] = {}
    unlabeled: list[EventFile] = []
    for ef in files:
        lab = _file_end_label(ef)
        if lab:
            buckets.setdefault(lab, []).append(ef)
        else:
            unlabeled.append(ef)

    order = ("INITIATOR", "LOCAL", "BACKUP", "REMOTE")
    groups: list[tuple[str, list[EventFile]]] = []
    seen: set[str] = set()
    for key in order:
        if key in buckets:
            groups.append((key, buckets[key]))
            seen.add(key)
    for key, fl in buckets.items():
        if key not in seen:
            groups.append((key, fl))

    if not groups:
        # No end labels: split by distinct CFG stems when multiple records exist
        cfgs = [
            ef
            for ef in files
            if (ef.original_filename or "").lower().endswith((".cfg", ".cff"))
        ]
        if len(cfgs) <= 1:
            return [("LOCAL", list(files))]
        by_stem: dict[str, list[EventFile]] = {}
        for ef in files:
            stem = Path(ef.original_filename or "").stem.lower()
            by_stem.setdefault(stem or "unknown", []).append(ef)
        # Prefer grouping COMTRADE pairs: cfg stem matches dat stem
        stems = sorted(by_stem.keys())
        for i, stem in enumerate(stems):
            label = "LOCAL" if i == 0 else (f"REMOTE_{i}" if i > 1 else "REMOTE")
            groups.append((label, by_stem[stem]))
        return groups

    if unlabeled and groups:
        # Attach unlabeled settings/SOE to the first (initiator/local) group
        groups[0] = (groups[0][0], list(groups[0][1]) + unlabeled)
    elif unlabeled:
        groups.append(("LOCAL", unlabeled))
    return groups


def _materialize_event_files(storage: StorageService, files: list[EventFile]) -> list[Path]:
    """Write COMTRADE-relevant event files to a temp dir for ingest.

    Skips ZIP packages and non-COMTRADE attachments so the original archive
    binary cannot confuse CFG/DAT detection. SEL ``.cev`` files are converted
    to CFG+DAT in the temp dir when derived files were not already uploaded.
    """
    from app.services.vendor_formats import cev_to_comtrade_files

    comtrade_exts = {".cfg", ".dat", ".cff", ".hdr", ".inf"}
    tmp = Path(tempfile.mkdtemp(prefix="wf_"))
    paths: list[Path] = []
    have_cfg_dat = False
    used_names: set[str] = set()
    for ef in files:
        name = ef.original_filename or f"{ef.sha256}.bin"
        ext = Path(name).suffix.lower()
        if ext not in comtrade_exts:
            continue
        if (ef.source_type or "").upper() == "PACKAGE":
            continue
        raw = storage.get_bytes(ef.storage_key)
        base = Path(name).name
        # Avoid collisions when both ends share the same CFG filename
        if base.lower() in used_names:
            base = f"{_file_end_label(ef) or 'END'}_{base}"
        used_names.add(base.lower())
        dest = tmp / base
        dest.write_bytes(raw)
        paths.append(dest)
        if ext in (".cfg", ".dat", ".cff"):
            have_cfg_dat = True

    # Convert CEV on the fly when no CFG/DAT/CFF already materialized
    if not have_cfg_dat:
        for ef in files:
            name = ef.original_filename or ""
            if not name.lower().endswith(".cev"):
                continue
            if (ef.source_type or "").upper() == "PACKAGE":
                continue
            raw = storage.get_bytes(ef.storage_key)
            converted = cev_to_comtrade_files(raw, basename=name)
            if converted.get("status") != "OK":
                logger.warning(
                    "CEV conversion skipped for %s: %s",
                    name,
                    converted.get("reason"),
                )
                continue
            cfg_p = tmp / converted["cfg_name"]
            dat_p = tmp / converted["dat_name"]
            cfg_p.write_text(converted["cfg"], encoding="utf-8", newline="\n")
            dat_p.write_text(converted["dat"], encoding="utf-8", newline="\n")
            paths.extend([cfg_p, dat_p])
            have_cfg_dat = True
            break

    return paths


async def _persist_one_comtrade_end(
    db: AsyncSession,
    event: Event,
    *,
    storage: StorageService,
    end_label: str,
    end_files: list[EventFile],
    record: Any,
    det: Any,
    val: Any,
) -> ComtradeFile:
    """Persist one parsed COMTRADE end (channels + sample cache)."""
    cfg_key = dat_key = None
    link_file_id = end_files[0].id if end_files else None
    for ef in end_files:
        name = (ef.original_filename or "").lower()
        if name.endswith(".cfg"):
            cfg_key = ef.storage_key
            link_file_id = ef.id
        elif name.endswith(".dat"):
            dat_key = ef.storage_key
        elif name.endswith(".cff"):
            cfg_key = ef.storage_key
            link_file_id = ef.id

    rev = getattr(det, "revision", None)
    revision_year = int(rev) if rev and str(rev).isdigit() else None
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
        event_file_id=link_file_id,
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
            "end_label": end_label,
            "cascade_role": end_label if end_label in ("INITIATOR", "BACKUP") else None,
        },
    )
    db.add(ct)
    await db.flush()

    timestamps = list(record.timestamps or [])
    scaled = record.scaled_values or {}
    raw = record.raw_values or {}
    max_points = max(100, int(get_settings().waveform_max_points or 20000))

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

    end_prefix = f"waveforms/{event.id}/{end_label}"
    ts_trim = _trim(timestamps)
    ts_key = _put_json(storage, ts_trim, prefix=end_prefix, suffix=".ts.json")

    for idx, ch in enumerate(record.analog_channels or []):
        name = ch.name if hasattr(ch, "name") else (ch.get("name") if isinstance(ch, dict) else f"A{idx}")
        units = getattr(ch, "unit", None) or getattr(ch, "units", None)
        if isinstance(ch, dict):
            units = ch.get("unit") or ch.get("units")
        phase = ch.phase if hasattr(ch, "phase") else (ch.get("phase") if isinstance(ch, dict) else None)
        samples = _channel_samples(str(name), analog=True)
        samples_trim = _trim(list(samples))
        sample_key = _put_json(
            storage,
            samples_trim,
            prefix=end_prefix,
            suffix=f".{_safe_channel_token(name)}.json",
        )
        ps = getattr(ch, "ps", None) if not isinstance(ch, dict) else ch.get("ps")
        primary = getattr(ch, "primary", None) if not isinstance(ch, dict) else ch.get("primary")
        secondary = (
            getattr(ch, "secondary", None) if not isinstance(ch, dict) else ch.get("secondary")
        )
        db.add(
            ComtradeChannel(
                comtrade_file_id=ct.id,
                channel_index=idx,
                channel_type="ANALOG",
                name=str(name),
                phase=phase,
                units=units,
                primary=float(primary) if primary is not None else None,
                secondary_ratio=float(secondary) if secondary is not None else None,
                ps=str(ps).upper()[:8] if ps else None,
                channel_metadata={
                    "sample_storage_key": sample_key,
                    "timestamp_storage_key": ts_key,
                    "sample_count": len(samples_trim),
                    "full_sample_count": len(samples),
                    "trimmed": len(samples) > len(samples_trim),
                    "ps": str(ps).upper() if ps else None,
                    "primary": primary,
                    "secondary": secondary,
                    "end_label": end_label,
                },
            )
        )

    for idx, ch in enumerate(record.digital_channels or []):
        name = ch.name if hasattr(ch, "name") else (ch.get("name") if isinstance(ch, dict) else f"D{idx}")
        samples = _channel_samples(str(name), analog=False)
        samples_trim = _trim(list(samples))
        sample_key = _put_json(
            storage,
            samples_trim,
            prefix=end_prefix,
            suffix=f".{_safe_channel_token(name)}.json",
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
                    "end_label": end_label,
                },
            )
        )

    if event.data_quality and not ct.data_quality:
        ct.data_quality = event.data_quality
    await db.flush()
    return ct


async def ingest_and_persist_comtrade(
    db: AsyncSession,
    event: Event,
    *,
    storage: Optional[StorageService] = None,
) -> dict[str, Any]:
    """Parse uploaded event files, persist ComtradeFile/Channel, cache samples.

    Combined Cascade / Local-Remote events: each end is ingested separately so both
    INITIATOR and BACKUP (or LOCAL/REMOTE) COMTRADE records are available for DR.
    """
    storage = storage or StorageService()
    files = (
        await db.execute(select(EventFile).where(EventFile.event_id == event.id))
    ).scalars().all()
    if not files:
        return {"success": False, "error": "No uploaded files", "status": "NOT_AVAILABLE"}

    from comtrade.service import ComtradeService

    svc = ComtradeService()
    groups = _group_files_by_end(list(files))

    # Remove prior comtrade rows for re-analyse
    existing = (
        await db.execute(select(ComtradeFile).where(ComtradeFile.event_id == event.id))
    ).scalars().all()
    for row in existing:
        await db.delete(row)
    await db.flush()

    persisted: list[dict[str, Any]] = []
    last_error: Optional[str] = None
    last_detection = None
    last_validation = None
    primary_record = None
    primary_ct: Optional[ComtradeFile] = None

    for end_label, end_files in groups:
        paths = _materialize_event_files(storage, end_files)
        if not paths:
            continue
        ingest = svc.ingest(paths, validate_after_parse=True)
        if not ingest.success or ingest.record is None:
            last_error = ingest.error or f"parse failed ({end_label})"
            last_detection = ingest.detection
            last_validation = ingest.validation
            logger.warning(
                "COMTRADE ingest failed for event %s end %s: %s",
                event.id,
                end_label,
                last_error,
            )
            continue
        ct = await _persist_one_comtrade_end(
            db,
            event,
            storage=storage,
            end_label=end_label,
            end_files=end_files,
            record=ingest.record,
            det=ingest.detection,
            val=ingest.validation,
        )
        persisted.append(
            {
                "end_label": end_label,
                "comtrade_file_id": ct.id,
                "analog": ct.analog_channel_count,
                "digital": ct.digital_channel_count,
                "samples": ct.total_samples,
            }
        )
        # Prefer INITIATOR/LOCAL as primary record for engineering pipeline
        if primary_ct is None or end_label in ("INITIATOR", "LOCAL"):
            primary_ct = ct
            primary_record = ingest.record
            last_detection = ingest.detection
            last_validation = ingest.validation
            if ingest.validation and getattr(ingest.validation, "data_quality", None):
                event.data_quality = ingest.validation.data_quality
            elif ingest.detection:
                event.data_quality = (
                    "ACCEPTABLE" if ingest.detection.status == "SUPPORTED" else "WARNING"
                )

    if not persisted:
        event.data_quality = (
            "INVALID"
            if last_detection and not getattr(last_detection, "is_comtrade", True)
            else "POOR"
        )
        return {
            "success": False,
            "error": last_error or "parse failed",
            "detection": last_detection.to_dict() if last_detection else None,
            "validation": last_validation.to_dict() if last_validation else None,
        }

    await db.flush()
    return {
        "success": True,
        "comtrade_file_id": primary_ct.id if primary_ct else persisted[0]["comtrade_file_id"],
        "analog": primary_ct.analog_channel_count if primary_ct else persisted[0]["analog"],
        "digital": primary_ct.digital_channel_count if primary_ct else persisted[0]["digital"],
        "samples": primary_ct.total_samples if primary_ct else persisted[0]["samples"],
        "ends": persisted,
        "ends_count": len(persisted),
        "validation": last_validation.to_dict() if last_validation else None,
        "detection": last_detection.to_dict() if last_detection else None,
        "record": primary_record,
    }


def _select_waveform_channels(
    channels: list[Any],
    *,
    max_channels: int,
) -> tuple[list[Any], Optional[str]]:
    """Keep protection digitals when capping — do not drop trailing status bits.

    Ordering in the DB is ANALOG then DIGITAL by index. A naive ``LIMIT 32`` on a
    15-analog / 21-digital 7UT record cuts off ``87G picked up`` and later bits.
    """
    if max_channels <= 0 or len(channels) <= max_channels:
        return list(channels), None

    digitals = [
        c
        for c in channels
        if str(getattr(c, "channel_type", "") or "").upper() == "DIGITAL"
    ]
    analogs = [
        c
        for c in channels
        if str(getattr(c, "channel_type", "") or "").upper() != "DIGITAL"
    ]
    # Reserve room for every digital when possible; otherwise keep first N digitals.
    dig_keep = min(len(digitals), max_channels)
    ana_keep = min(len(analogs), max(0, max_channels - dig_keep))
    # If digitals alone exceed the cap, still prefer digitals over analogs.
    if dig_keep + ana_keep < max_channels and ana_keep < len(analogs):
        ana_keep = min(len(analogs), max_channels - dig_keep)
    selected = analogs[:ana_keep] + digitals[:dig_keep]
    selected.sort(
        key=lambda c: (
            0 if str(getattr(c, "channel_type", "") or "").upper() != "DIGITAL" else 1,
            int(getattr(c, "channel_index", 0) or 0),
        )
    )
    dropped = len(channels) - len(selected)
    note = (
        f"Showing {len(selected)} of {len(channels)} channels "
        f"({ana_keep} analog, {dig_keep} digital; {dropped} omitted)."
        if dropped
        else None
    )
    return selected, note


async def load_waveform_payload(
    db: AsyncSession,
    event_id: str,
    *,
    storage: Optional[StorageService] = None,
    max_channels: Optional[int] = None,
    comtrade_file_id: Optional[str] = None,
) -> dict[str, Any]:
    storage = storage or StorageService()
    if max_channels is None:
        max_channels = max(8, int(get_settings().waveform_max_channels or 128))
    if comtrade_file_id:
        ct = (
            await db.execute(
                select(ComtradeFile).where(
                    ComtradeFile.event_id == event_id,
                    ComtradeFile.id == comtrade_file_id,
                )
            )
        ).scalar_one_or_none()
    else:
        # Prefer INITIATOR / LOCAL when multiple ends exist (cascade / multi-end)
        rows = (
            await db.execute(
                select(ComtradeFile)
                .where(ComtradeFile.event_id == event_id)
                .order_by(ComtradeFile.created_at.asc())
            )
        ).scalars().all()
        ct = None
        for row in rows:
            hdr = row.header_metadata if isinstance(row.header_metadata, dict) else {}
            lab = str(hdr.get("end_label") or hdr.get("cascade_role") or "").upper()
            if lab in ("INITIATOR", "LOCAL"):
                ct = row
                break
        if ct is None and rows:
            ct = rows[0]

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

    all_channels = (
        await db.execute(
            select(ComtradeChannel)
            .where(ComtradeChannel.comtrade_file_id == ct.id)
            .order_by(ComtradeChannel.channel_type, ComtradeChannel.channel_index)
        )
    ).scalars().all()
    channels, channel_cap_note = _select_waveform_channels(
        list(all_channels), max_channels=max_channels
    )

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
                "ps": c.ps or (meta.get("ps") if isinstance(meta, dict) else None),
                "primary": c.primary
                if c.primary is not None
                else (meta.get("primary") if isinstance(meta, dict) else None),
                "secondary": c.secondary_ratio
                if c.secondary_ratio is not None
                else (meta.get("secondary") if isinstance(meta, dict) else None),
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

    note: Optional[str] = None
    if not any((c.get("samples") or []) for c in out):
        note = "Channels present but samples not cached"
    elif channel_cap_note:
        note = channel_cap_note

    return {
        "event_id": event_id,
        "channels": out,
        "markers": markers,
        "note": note,
        "comtrade_file_id": ct.id,
        "validation_status": ct.validation_status,
        "data_quality": ct.data_quality,
    }
