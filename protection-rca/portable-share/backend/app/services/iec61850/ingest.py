"""Turn an IEC 61850 acquisition result into events + stored files (manual and auto fetch)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Relay
from app.schemas.events import EventCreate
from app.services import event_service, file_service
from app.services.audit_service import write_audit
from app.services.iec61850 import acquire as acq

MAX_FETCHED_INDEX = 500


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
) -> list[dict[str, Any]]:
    """One event per downloaded record (or one settings/events-only event)."""
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
                event_datetime=when or datetime.now(timezone.utc),
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
        for p in [*payloads, *result.shared]:
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
