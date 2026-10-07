"""Turn an IEC 61850 acquisition result into events + stored files (manual and auto fetch)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Event, Relay
from app.schemas.events import EventCreate
from app.services import event_service, file_service
from app.services.audit_service import write_audit
from app.services.iec61850 import acquire as acq
from app.services.side_files import (
    dr_soe_window,
    filter_soe_csv_bytes,
    soe_file_matches_record,
)

MAX_FETCHED_INDEX = 500
# Fallback window when CFG trigger time is unknown (seconds around file mtime)
_DEFAULT_DR_DURATION_S = 2.0


def _shared_for_record(
    shared: list[acq.Payload],
    *,
    record_key: Optional[str],
    record_when: Optional[datetime],
) -> list[acq.Payload]:
    """Attach settings to every DR; keep only SOE/event rows that match this DR.

    Matching (market-tool style):
    1. Filename contains the COMTRADE record stem → belong to that DR only
    2. Else SOE CSV → keep rows inside [DR − 5 s … DR end + 30 s]
    3. Settings / SCL → always shared
    """
    if not shared:
        return []
    out: list[acq.Payload] = []
    window = None
    if record_when is not None:
        window = dr_soe_window(record_when, duration_s=_DEFAULT_DR_DURATION_S)

    for p in shared:
        st = (p.source_type or "").upper()
        name = (p.filename or "").lower()

        always = st in ("SETTINGS", "ATTACHMENT") or name.endswith(
            (".set", ".rdb", ".xrio", ".rio", ".cid", ".icd", ".scd", ".iid", ".ssd")
        ) or (name.endswith(".json") and "soe" not in name and "ser" not in name)
        if always:
            out.append(p)
            continue

        if record_key and soe_file_matches_record(p.filename or "", record_key):
            out.append(p)
            continue

        is_soe = st == "SOE" or name.endswith(".csv") or "soe" in name or "ser" in name
        if is_soe and window is not None and (
            name.endswith(".csv") or st == "SOE" or "soe" in name or "ser" in name
        ):
            try:
                sliced = filter_soe_csv_bytes(
                    p.data, window_start=window[0], window_end=window[1]
                )
            except Exception:  # noqa: BLE001
                sliced = p.data
            out.append(
                acq.Payload(
                    filename=p.filename,
                    data=sliced,
                    remote_path=p.remote_path,
                    source_type=p.source_type or "SOE",
                )
            )
            continue

        # Untimed / unmatched event logs: do not copy the whole IED history onto every DR
        if is_soe or st == "RELAY_EVENT_REPORT":
            if window is None and not record_key:
                out.append(p)
            continue

        out.append(p)
    return out


def saved_config(relay: Relay) -> dict[str, Any]:
    meta = relay.metadata_json if isinstance(relay.metadata_json, dict) else {}
    return dict(meta.get("iec61850") or {})


def save_config(relay: Relay, **updates: Any) -> None:
    meta = dict(relay.metadata_json) if isinstance(relay.metadata_json, dict) else {}
    cur = dict(meta.get("iec61850") or {})
    cur.update({k: v for k, v in updates.items() if v is not None})
    meta["iec61850"] = cur
    relay.metadata_json = meta  # reassign so the JSON column is flagged dirty


def persist_connection(relay: Relay, conn: acq.Connection) -> None:
    relay.ip_address = conn.host
    save_config(
        relay,
        port=conn.port,
        vendor_profile=conn.profile_id,
        remote_directory=conn.remote_directory or "",
        connect_timeout_s=conn.connect_timeout_s,
        request_timeout_s=conn.request_timeout_s,
    )


def remember_success(relay: Relay, conn: acq.Connection, nameplate: dict[str, Any]) -> None:
    persist_connection(relay, conn)
    save_config(relay, last_nameplate=nameplate, last_seen_at=datetime.now(timezone.utc).isoformat())
    if nameplate.get("vendor") and not relay.manufacturer:
        relay.manufacturer = str(nameplate["vendor"])[:128]
    if nameplate.get("model") and not relay.model:
        relay.model = str(nameplate["model"])[:128]
    if nameplate.get("swRev") and not relay.firmware_version:
        relay.firmware_version = str(nameplate["swRev"])[:64]
    if nameplate.get("serNum") and not relay.serial_number:
        relay.serial_number = str(nameplate["serNum"])[:128]


async def create_events(
    db: AsyncSession,
    relay: Relay,
    conn: acq.Connection,
    result: acq.AcquireResult,
    *,
    description: Optional[str],
    user_id: Optional[str],
    request_id: Optional[str],
    trigger: str,
    end_label: str = "LOCAL",
) -> list[dict[str, Any]]:
    """One event per downloaded record (or one settings/events-only event)."""
    label = (end_label or "LOCAL").strip().upper() or "LOCAL"
    groups: list[tuple[Optional[str], list[acq.Payload]]] = list(result.records.items())
    if not groups:
        if not result.shared:
            return []
        groups = [(None, [])]

    created: list[dict[str, Any]] = []
    fetched_index = dict(saved_config(relay).get("fetched") or {})
    for key, payloads in groups:
        when: Optional[datetime] = None
        stamp = result.record_times.get(key) if key else None
        if stamp:
            try:
                when = datetime.fromisoformat(stamp)
            except ValueError:
                when = None
        record_name = payloads[0].remote_path if payloads else None
        label = "IEC 61850 auto-fetch" if trigger == "AUTO" else "IEC 61850 fetch"
        desc = description or (
            f"{label} from {conn.host}:{conn.port}"
            + (f" — {record_name.rsplit('.', 1)[0]}" if record_name else " — settings / events")
        )
        event = await event_service.create_event(
            db,
            EventCreate(
                relay_id=relay.id,
                description=desc[:1000],
                # Only stamp relay DR time when the IED provided a record timestamp.
                # Otherwise leave null — analysis fills from COMTRADE trigger/start.
                event_datetime=when,
                extra={
                    "acquisition": {
                        "method": "IEC61850_MMS",
                        "trigger": trigger,
                        "host": conn.host,
                        "port": conn.port,
                        "vendor_profile": result.profile.id if result.profile else conn.profile_id,
                        "nameplate": result.nameplate,
                        "record": key,
                        "warnings": result.warnings[:20],
                    }
                },
            ),
            engineer_id=user_id,
            request_id=request_id,
        )
        stored_names: list[str] = []
        source_types: set[str] = set()
        side = _shared_for_record(result.shared, record_key=key, record_when=when)
        for p in [*payloads, *side]:
            efs = await file_service.store_acquired_bytes(
                db,
                event,
                filename=p.filename,
                data=p.data,
                source_type=p.source_type,
                uploaded_by=user_id,
                request_id=request_id,
                file_metadata={
                    "acquired_via": "IEC61850",
                    "trigger": trigger,
                    "ied_host": conn.host,
                    "ied_path": p.remote_path,
                    "end_label": label,
                    "relay_id": relay.id,
                },
            )
            for ef in efs:
                stored_names.append(ef.original_filename)
                source_types.add((ef.source_type or "").upper())
        if key:
            fetched_index[key] = event.id
        created.append(
            {
                "id": event.id,
                "event_id": event.event_id,
                "record": key,
                "files": stored_names,
                "package_ready": "COMTRADE" in source_types and "SETTINGS" in source_types,
            }
        )

    if len(fetched_index) > MAX_FETCHED_INDEX:
        fetched_index = dict(list(fetched_index.items())[-MAX_FETCHED_INDEX:])
    save_config(relay, fetched=fetched_index)
    await write_audit(
        db,
        action="IEC61850_AUTO_FETCH" if trigger == "AUTO" else "IEC61850_FETCH",
        user_id=user_id,
        object_type="Relay",
        object_id=relay.id,
        new_value={
            "host": conn.host,
            "port": conn.port,
            "records": list(result.records),
            "events": [c["id"] for c in created],
        },
        request_id=request_id,
    )
    await db.flush()
    return created


async def store_payloads_on_event(
    db: AsyncSession,
    event: Event,
    relay: Relay,
    conn: acq.Connection,
    payloads: list[acq.Payload],
    *,
    end_label: str = "REMOTE",
    user_id: Optional[str] = None,
    request_id: Optional[str] = None,
    trigger: str = "AUTO_REMOTE",
) -> list[str]:
    """Append acquired payloads onto an existing event with the given end_label."""
    label = (end_label or "REMOTE").strip().upper() or "REMOTE"
    stored_names: list[str] = []
    for p in payloads:
        efs = await file_service.store_acquired_bytes(
            db,
            event,
            filename=p.filename,
            data=p.data,
            source_type=p.source_type,
            uploaded_by=user_id,
            request_id=request_id,
            file_metadata={
                "acquired_via": "IEC61850",
                "trigger": trigger,
                "ied_host": conn.host,
                "ied_path": p.remote_path,
                "end_label": label,
                "relay_id": relay.id,
            },
        )
        for ef in efs:
            stored_names.append(ef.original_filename)
    await db.flush()
    return stored_names
