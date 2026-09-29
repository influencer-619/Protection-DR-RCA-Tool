"""IEC 61850 acquisition API — pull DR / settings / events from an IED over MMS.

Read-only: only ACSI read and file-get services are used. No controls,
writes or file deletions are ever sent to the IED.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.config import get_settings
from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import Relay, User
from app.schemas.iec61850 import (
    FetchedEventOut,
    Iec61850AutoFetchIn,
    Iec61850AutoFetchOut,
    Iec61850Connection,
    Iec61850ConnectionOut,
    Iec61850FetchOut,
    Iec61850FetchRequest,
    Iec61850InfoOut,
    VendorProfileOut,
)
from app.services.iec61850 import acquire as acq
from app.services.iec61850 import auto_fetch
from app.services.iec61850.client import Iec61850Error, Iec61850Unavailable, library_status
from app.services.iec61850.ingest import (
    create_events,
    persist_connection,
    remember_success,
    saved_config,
)
from app.services.iec61850.vendors import PROFILES

router = APIRouter(prefix="/api", tags=["iec61850"])


def _connection_out(relay: Relay) -> Iec61850ConnectionOut:
    s = saved_config(relay)
    return Iec61850ConnectionOut(
        host=relay.ip_address,
        port=int(s.get("port") or 102),
        vendor_profile=s.get("vendor_profile") or "AUTO",
        connect_timeout_s=float(s.get("connect_timeout_s") or 10.0),
        request_timeout_s=float(s.get("request_timeout_s") or 20.0),
        last_nameplate=s.get("last_nameplate"),
        last_seen_at=s.get("last_seen_at"),
    )


def _auto_out(relay: Relay) -> Iec61850AutoFetchOut:
    cfg = auto_fetch.get_auto_config(relay)
    return Iec61850AutoFetchOut(
        scheduler_running=auto_fetch.scheduler_running(),
        interval_choices=list(auto_fetch.INTERVAL_CHOICES_MIN),
        **{k: cfg.get(k) for k in Iec61850AutoFetchOut.model_fields if k in cfg},
    )


async def _relay(db: DbSession, ied_id: str) -> Relay:
    relay = await db.get(Relay, ied_id)
    if relay is None:
        raise HTTPException(status_code=404, detail="IED not found")
    return relay


def _resolve(relay: Relay, body: Iec61850Connection) -> acq.Connection:
    saved = _connection_out(relay)
    host = body.host or saved.host
    if not host:
        raise HTTPException(status_code=400, detail="Enter the IED IP address first")
    return acq.Connection(
        host=host,
        port=body.port or saved.port,
        profile_id=(body.vendor_profile or saved.vendor_profile or "AUTO").upper(),
        connect_timeout_s=body.connect_timeout_s or saved.connect_timeout_s,
        request_timeout_s=body.request_timeout_s or saved.request_timeout_s,
    )


async def _run(fn, *args, **kwargs):
    try:
        return await asyncio.to_thread(fn, *args, **kwargs)
    except Iec61850Unavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Iec61850Error as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/iec61850/info", response_model=Iec61850InfoOut)
async def iec61850_info(user: CurrentUser) -> Iec61850InfoOut:
    return Iec61850InfoOut(
        library=library_status(),
        vendors=[VendorProfileOut(id=p.id, label=p.label, families=p.families, notes=p.notes) for p in PROFILES],
    )


@router.get("/ieds/{ied_id}/iec61850", response_model=Iec61850ConnectionOut)
async def get_connection(ied_id: str, db: DbSession, user: CurrentUser) -> Iec61850ConnectionOut:
    return _connection_out(await _relay(db, ied_id))


@router.put("/ieds/{ied_id}/iec61850", response_model=Iec61850ConnectionOut)
async def save_connection(
    ied_id: str,
    body: Iec61850Connection,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> Iec61850ConnectionOut:
    relay = await _relay(db, ied_id)
    persist_connection(relay, _resolve(relay, body))
    await db.flush()
    return _connection_out(relay)


@router.post("/ieds/{ied_id}/iec61850/test")
async def test_connection(
    ied_id: str,
    body: Iec61850Connection,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    relay = await _relay(db, ied_id)
    conn = _resolve(relay, body)
    await db.commit()  # don't hold a DB transaction open while waiting on the IED
    info = await _run(acq.identify, conn)
    remember_success(relay, conn, info["nameplate"])
    return info


@router.post("/ieds/{ied_id}/iec61850/browse")
async def browse_ied(
    ied_id: str,
    body: Iec61850Connection,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> dict[str, Any]:
    relay = await _relay(db, ied_id)
    conn = _resolve(relay, body)
    await db.commit()  # don't hold a DB transaction open while waiting on the IED
    result = await _run(acq.browse, conn)
    remember_success(relay, conn, result["nameplate"])
    fetched = saved_config(relay).get("fetched") or {}
    for rec in result["records"]:
        rec["event_id"] = fetched.get(rec["key"])
    return result


@router.post("/ieds/{ied_id}/iec61850/fetch", response_model=Iec61850FetchOut)
async def fetch_from_ied(
    ied_id: str,
    body: Iec61850FetchRequest,
    request: Request,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> Iec61850FetchOut:
    if not (body.records or body.include_settings or body.include_events or body.include_scl):
        raise HTTPException(status_code=400, detail="Select at least one record, or settings / events")
    relay = await _relay(db, ied_id)
    conn = _resolve(relay, body)
    settings = get_settings()
    await db.commit()  # don't hold a DB transaction open while waiting on the IED

    result = await _run(
        acq.acquire,
        conn,
        record_keys=body.records,
        include_settings=body.include_settings,
        include_events=body.include_events,
        include_scl=body.include_scl,
        ied_label=relay.relay_tag or relay.name,
        allowed_exts=set(settings.allowed_extensions),
        max_bytes=settings.max_upload_bytes,
    )
    remember_success(relay, conn, result.nameplate)
    created = await create_events(
        db,
        relay,
        conn,
        result,
        description=body.description,
        user_id=user.id,
        request_id=getattr(request.state, "request_id", None),
        trigger="MANUAL",
    )
    if not created:
        raise HTTPException(
            status_code=404,
            detail="Nothing was retrieved from the IED. " + "; ".join(result.warnings[:5]),
        )
    return Iec61850FetchOut(
        events=[FetchedEventOut(**c) for c in created],
        warnings=result.warnings,
        nameplate=result.nameplate,
        profile=result.profile.id if result.profile else None,
    )


@router.get("/ieds/{ied_id}/iec61850/auto-fetch", response_model=Iec61850AutoFetchOut)
async def get_auto_fetch(ied_id: str, db: DbSession, user: CurrentUser) -> Iec61850AutoFetchOut:
    return _auto_out(await _relay(db, ied_id))


@router.put("/ieds/{ied_id}/iec61850/auto-fetch", response_model=Iec61850AutoFetchOut)
async def save_auto_fetch(
    ied_id: str,
    body: Iec61850AutoFetchIn,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> Iec61850AutoFetchOut:
    relay = await _relay(db, ied_id)
    if body.host or body.port or body.vendor_profile:
        persist_connection(relay, _resolve(relay, body))
    if body.enabled and not relay.ip_address:
        raise HTTPException(status_code=400, detail="Enter the IED IP address before enabling auto-fetch")
    if body.interval_min not in auto_fetch.INTERVAL_CHOICES_MIN:
        raise HTTPException(status_code=400, detail="Unsupported check interval")
    before = auto_fetch.get_auto_config(relay)
    updates: dict[str, Any] = {
        "enabled": body.enabled,
        "interval_min": body.interval_min,
        "include_settings": body.include_settings,
        "include_events": body.include_events,
        "auto_analyse": body.auto_analyse,
        "import_existing": body.import_existing,
    }
    if body.enabled and not before.get("enabled"):
        # Fresh enable: take a new baseline and check right away.
        updates.update(baseline_done=False, skip_keys=[], record_failures={}, next_run_at=None)
    elif body.interval_min != before.get("interval_min"):
        updates["next_run_at"] = None
    auto_fetch.set_auto_config(relay, **updates)
    await db.flush()
    return _auto_out(relay)


@router.post("/ieds/{ied_id}/iec61850/auto-fetch/run-now", response_model=Iec61850AutoFetchOut)
async def run_auto_fetch_now(
    ied_id: str,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> Iec61850AutoFetchOut:
    relay = await _relay(db, ied_id)
    if not library_status()["available"]:
        raise HTTPException(status_code=503, detail="IEC 61850 client library is not installed on the server")
    await db.commit()
    outcome = await auto_fetch.run_cycle(relay.id)
    if outcome.get("status") == "BUSY":
        raise HTTPException(status_code=409, detail=outcome["message"])
    await db.refresh(relay)
    return _auto_out(relay)
