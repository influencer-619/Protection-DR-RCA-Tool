"""Background auto-fetch: poll enabled IEDs and ingest new disturbance records.

Config lives on the relay: ``metadata.iec61850.auto_fetch``. Runs inside the
API process (single-instance deployments such as the portable build).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy import select

from app.core.config import get_settings
from app.database import AsyncSessionLocal
from app.models import Relay
from app.services.iec61850 import acquire as acq
from app.services.iec61850.client import Iec61850Error, Iec61850Unavailable, library_status
from app.services.iec61850.ingest import (
    create_events,
    remember_success,
    save_config,
    saved_config,
    store_payloads_on_event,
)
from app.services import remote_peer

logger = logging.getLogger(__name__)

TICK_SECONDS = 30
MAX_RECORDS_PER_CYCLE = 10
MAX_SKIP_KEYS = 2000
MAX_RECORD_FAILURES = 3
PARALLEL_IEDS = 4
INTERVAL_CHOICES_MIN = (1, 2, 5, 10, 15, 30, 60, 120, 240)

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "interval_min": 5,
    "include_settings": True,
    "include_events": True,
    "auto_analyse": True,
    "import_existing": False,
    "also_fetch_remote": False,
}

_running: set[str] = set()
_task: Optional[asyncio.Task] = None
_background: set[asyncio.Task] = set()


def scheduler_running() -> bool:
    return _task is not None and not _task.done()


def get_auto_config(relay: Relay) -> dict[str, Any]:
    cfg = dict(DEFAULTS)
    cfg.update(saved_config(relay).get("auto_fetch") or {})
    return cfg


def set_auto_config(relay: Relay, **updates: Any) -> dict[str, Any]:
    cfg = get_auto_config(relay)
    cfg.update(updates)
    save_config(relay, auto_fetch=cfg)
    return cfg


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_due(cfg: dict[str, Any]) -> bool:
    nxt = cfg.get("next_run_at")
    if not nxt:
        return True
    try:
        return datetime.fromisoformat(nxt) <= _now()
    except ValueError:
        return True


def _connection(relay: Relay) -> Optional[acq.Connection]:
    saved = saved_config(relay)
    if not relay.ip_address:
        return None
    return acq.Connection(
        host=relay.ip_address,
        port=int(saved.get("port") or 102),
        profile_id=str(saved.get("vendor_profile") or "AUTO").upper(),
        connect_timeout_s=float(saved.get("connect_timeout_s") or 10.0),
        request_timeout_s=float(saved.get("request_timeout_s") or 20.0),
        remote_directory=(saved.get("remote_directory") or None) or None,
    )


async def run_cycle(relay_id: str) -> dict[str, Any]:
    """One poll of one IED. Safe to call from the API ("Check now")."""
    if relay_id in _running:
        return {"status": "BUSY", "message": "A check is already running for this IED"}
    _running.add(relay_id)
    try:
        return await _run_cycle(relay_id)
    finally:
        _running.discard(relay_id)


async def _run_cycle(relay_id: str) -> dict[str, Any]:
    settings = get_settings()
    async with AsyncSessionLocal() as db:
        relay = await db.get(Relay, relay_id)
        if relay is None:
            return {"status": "ERROR", "message": "IED not found"}
        cfg = get_auto_config(relay)
        conn = _connection(relay)
        started = _now()
        interval = max(1, int(cfg.get("interval_min") or 5))
        status: dict[str, Any] = {
            "last_run_at": started.isoformat(),
            "next_run_at": (started + timedelta(minutes=interval)).isoformat(),
        }
        if conn is None:
            status.update(last_status="ERROR", last_error="No IP address saved for this IED")
            set_auto_config(relay, **status)
            await db.commit()
            return status
        ied_label = relay.relay_tag or relay.name
        fetched = set((saved_config(relay).get("fetched") or {}).keys())
        skip = set(cfg.get("skip_keys") or [])
        failures: dict[str, int] = dict(cfg.get("record_failures") or {})
        baseline_done = bool(cfg.get("baseline_done"))
        await db.commit()

        created: list[dict[str, Any]] = []
        try:
            listing = await asyncio.to_thread(acq.browse, conn)
            complete = [r for r in listing["records"] if r["complete"]]
            if not baseline_done and not cfg.get("import_existing"):
                skip |= {r["key"] for r in complete}
                new_keys: list[str] = []
            else:
                new = [r for r in complete if r["key"] not in fetched and r["key"] not in skip]
                new.sort(key=lambda r: r["last_modified_ms"])  # oldest first → chronological events
                new_keys = [r["key"] for r in new[:MAX_RECORDS_PER_CYCLE]]

            if new_keys:
                result = await asyncio.to_thread(
                    acq.acquire,
                    conn,
                    record_keys=new_keys,
                    include_settings=bool(cfg.get("include_settings")),
                    include_events=bool(cfg.get("include_events")),
                    include_scl=False,
                    ied_label=ied_label,
                    allowed_exts=set(settings.allowed_extensions),
                    max_bytes=settings.max_upload_bytes,
                )
                await db.refresh(relay)
                remember_success(relay, conn, result.nameplate)
                created = await create_events(
                    db,
                    relay,
                    conn,
                    result,
                    description=None,
                    user_id=None,
                    request_id=None,
                    trigger="AUTO",
                    end_label="LOCAL",
                )
                for k in new_keys:
                    if k in result.records:
                        failures.pop(k, None)
                    else:
                        failures[k] = failures.get(k, 0) + 1
                        if failures[k] >= MAX_RECORD_FAILURES:
                            skip.add(k)
                            failures.pop(k)
                if created and cfg.get("also_fetch_remote"):
                    remote_note = await _fetch_remote_into_events(
                        db,
                        local_relay=relay,
                        created=created,
                        include_settings=bool(cfg.get("include_settings")),
                        include_events=bool(cfg.get("include_events")),
                    )
                    if remote_note:
                        status["remote_fetch"] = remote_note
            else:
                await db.refresh(relay)
                remember_success(relay, conn, listing["nameplate"])

            status.update(
                last_status="OK",
                last_error=None,
                last_new_records=len(created),
                records_on_ied=len(listing["records"]),
                total_events_created=int(cfg.get("total_events_created") or 0) + len(created),
                baseline_done=True,
                skip_keys=sorted(skip)[-MAX_SKIP_KEYS:],
                record_failures=failures,
            )
            if created:
                status["last_event_at"] = _now().isoformat()
        except (Iec61850Error, Iec61850Unavailable, OSError) as exc:
            await db.refresh(relay)
            status.update(last_status="ERROR", last_error=str(exc)[:500])
        except Exception as exc:  # noqa: BLE001
            logger.exception("IEC 61850 auto-fetch failed for %s", relay_id)
            await db.refresh(relay)
            status.update(last_status="ERROR", last_error=f"Internal error: {exc}"[:500])

        set_auto_config(relay, **status)
        await db.commit()

        if created and cfg.get("auto_analyse"):
            await _start_analysis(db, [c for c in created if c["package_ready"]])
        return {**status, "events": created}


async def _fetch_remote_into_events(
    db,
    *,
    local_relay: Relay,
    created: list[dict[str, Any]],
    include_settings: bool,
    include_events: bool,
) -> dict[str, Any]:
    """Opt-in: pull peer IED records into the same events as REMOTE. Never fails the local cycle."""
    settings = get_settings()
    peer = await remote_peer.resolve_remote_relay(db, local_relay)
    if peer is None:
        return {"status": "SKIPPED", "message": "No remote IED configured"}
    peer_conn = _connection(peer)
    if peer_conn is None:
        return {"status": "SKIPPED", "message": f"Remote IED {peer.relay_tag} has no IP"}
    try:
        listing = await asyncio.to_thread(acq.browse, peer_conn)
        complete = [r for r in listing["records"] if r["complete"]]
        peer_fetched = set((saved_config(peer).get("fetched") or {}).keys())
        peer_cfg = get_auto_config(peer)
        peer_skip = set(peer_cfg.get("skip_keys") or [])
        candidates = [
            r for r in complete if r["key"] not in peer_fetched and r["key"] not in peer_skip
        ]
        candidates.sort(key=lambda r: r["last_modified_ms"])
        # Pair oldest-first with each local event (same order as local create_events)
        keys = [r["key"] for r in candidates[: len(created)]]
        if not keys:
            return {
                "status": "OK",
                "message": "No new remote records to pair",
                "remote_ied": peer.relay_tag,
                "files_added": 0,
            }
        result = await asyncio.to_thread(
            acq.acquire,
            peer_conn,
            record_keys=keys,
            include_settings=include_settings,
            include_events=include_events,
            include_scl=False,
            ied_label=peer.relay_tag or peer.name,
            allowed_exts=set(settings.allowed_extensions),
            max_bytes=settings.max_upload_bytes,
        )
        await db.refresh(peer)
        remember_success(peer, peer_conn, result.nameplate)
        from app.services import event_service

        files_added = 0
        peer_fetched_index = dict(saved_config(peer).get("fetched") or {})
        for ev_info, key in zip(created, keys):
            payloads = list(result.records.get(key) or [])
            if not payloads:
                continue
            event = await event_service.get_event(db, ev_info["id"])
            if event is None:
                continue
            names = await store_payloads_on_event(
                db,
                event,
                peer,
                peer_conn,
                payloads,
                end_label="REMOTE",
                trigger="AUTO_REMOTE",
            )
            files_added += len(names)
            peer_fetched_index[key] = event.id
            # Mark package_ready if remote brought COMTRADE
            if any((p.source_type or "").upper() == "COMTRADE" for p in payloads):
                ev_info["package_ready"] = True
                ev_info.setdefault("files", []).extend(names)
        if len(peer_fetched_index) > 500:
            peer_fetched_index = dict(list(peer_fetched_index.items())[-500:])
        save_config(peer, fetched=peer_fetched_index)
        await db.flush()
        return {
            "status": "OK",
            "remote_ied": peer.relay_tag or peer.name,
            "records": len(keys),
            "files_added": files_added,
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Also-fetch remote IED failed for local %s: %s",
            local_relay.id,
            exc,
        )
        return {"status": "ERROR", "message": str(exc)[:400]}


async def _start_analysis(db, created: list[dict[str, Any]]) -> None:
    from app.services import analysis_service, event_service

    for c in created:
        try:
            event = await event_service.get_event(db, c["id"])
            if event is None:
                continue
            job = await analysis_service.enqueue_analysis(db, event, defer=True)
            await db.commit()
            if job.status == "PENDING":
                t = asyncio.create_task(analysis_service.run_job_by_id(job.id))
                _background.add(t)
                t.add_done_callback(_background.discard)
        except Exception:  # noqa: BLE001
            logger.exception("Auto-analysis could not be queued for event %s", c["id"])


async def _tick() -> None:
    async with AsyncSessionLocal() as db:
        relays = (await db.execute(select(Relay).where(Relay.ip_address.is_not(None)))).scalars().all()
        due = [
            r.id
            for r in relays
            if get_auto_config(r).get("enabled") and _is_due(get_auto_config(r)) and r.id not in _running
        ]
    if not due:
        return
    sem = asyncio.Semaphore(PARALLEL_IEDS)

    async def one(rid: str) -> None:
        async with sem:
            await run_cycle(rid)

    await asyncio.gather(*(one(rid) for rid in due), return_exceptions=True)


async def _loop() -> None:
    logger.info("IEC 61850 auto-fetch scheduler started")
    while True:
        try:
            await _tick()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("IEC 61850 auto-fetch tick failed")
        await asyncio.sleep(TICK_SECONDS)


def start_scheduler() -> None:
    global _task
    if not get_settings().iec61850_auto_fetch or not library_status()["available"]:
        return
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop_scheduler() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
        _task = None
