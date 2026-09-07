"""Asset hierarchy API — substations, bays, relays, breakers, assets."""

from __future__ import annotations

from typing import Annotated

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import Asset, Bay, Breaker, Relay, Substation
from app.schemas.assets import (
    AssetCreate,
    AssetOut,
    BayCreate,
    BayOut,
    BreakerCreate,
    BreakerOut,
    RelayCreate,
    RelayOut,
    SubstationCreate,
    SubstationOut,
)

router = APIRouter(prefix="/api", tags=["assets"])


# --- Substations ---


@router.post("/substations", response_model=SubstationOut, status_code=status.HTTP_201_CREATED)
async def create_substation(
    body: SubstationCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> SubstationOut:
    obj = Substation(**body.model_dump(exclude_unset=True))
    db.add(obj)
    await db.flush()
    return SubstationOut.model_validate(obj)


@router.get("/substations", response_model=list[SubstationOut])
async def list_substations(db: DbSession, user: CurrentUser) -> list[SubstationOut]:
    rows = (await db.execute(select(Substation).order_by(Substation.code))).scalars().all()
    return [SubstationOut.model_validate(r) for r in rows]


@router.get("/substations/{substation_id}", response_model=SubstationOut)
async def get_substation(
    substation_id: str, db: DbSession, user: CurrentUser
) -> SubstationOut:
    row = await db.get(Substation, substation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Substation not found")
    return SubstationOut.model_validate(row)


# --- Bays ---


@router.post("/bays", response_model=BayOut, status_code=status.HTTP_201_CREATED)
async def create_bay(
    body: BayCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> BayOut:
    obj = Bay(**body.model_dump(exclude_unset=True))
    db.add(obj)
    await db.flush()
    return BayOut.model_validate(obj)


@router.get("/bays", response_model=list[BayOut])
async def list_bays(
    db: DbSession,
    user: CurrentUser,
    substation_id: Optional[str] = None,
) -> list[BayOut]:
    q = select(Bay)
    if substation_id:
        q = q.where(Bay.substation_id == substation_id)
    rows = (await db.execute(q.order_by(Bay.code))).scalars().all()
    return [BayOut.model_validate(r) for r in rows]


# --- Relays ---


@router.post("/relays", response_model=RelayOut, status_code=status.HTTP_201_CREATED)
async def create_relay(
    body: RelayCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> RelayOut:
    obj = Relay(**body.model_dump(exclude_unset=True))
    db.add(obj)
    await db.flush()
    return RelayOut.model_validate(obj)


@router.get("/relays", response_model=list[RelayOut])
async def list_relays(
    db: DbSession,
    user: CurrentUser,
    substation_id: Optional[str] = None,
    bay_id: Optional[str] = None,
) -> list[RelayOut]:
    q = select(Relay)
    if substation_id:
        q = q.where(Relay.substation_id == substation_id)
    if bay_id:
        q = q.where(Relay.bay_id == bay_id)
    rows = (await db.execute(q.order_by(Relay.relay_tag))).scalars().all()
    return [RelayOut.model_validate(r) for r in rows]


@router.get("/relays/{relay_id}", response_model=RelayOut)
async def get_relay(relay_id: str, db: DbSession, user: CurrentUser) -> RelayOut:
    row = await db.get(Relay, relay_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Relay not found")
    return RelayOut.model_validate(row)


# --- Breakers ---


@router.post("/breakers", response_model=BreakerOut, status_code=status.HTTP_201_CREATED)
async def create_breaker(
    body: BreakerCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> BreakerOut:
    obj = Breaker(**body.model_dump(exclude_unset=True))
    db.add(obj)
    await db.flush()
    return BreakerOut.model_validate(obj)


@router.get("/breakers", response_model=list[BreakerOut])
async def list_breakers(
    db: DbSession,
    user: CurrentUser,
    substation_id: Optional[str] = None,
) -> list[BreakerOut]:
    q = select(Breaker)
    if substation_id:
        q = q.where(Breaker.substation_id == substation_id)
    rows = (await db.execute(q.order_by(Breaker.breaker_tag))).scalars().all()
    return [BreakerOut.model_validate(r) for r in rows]


# --- Assets ---


@router.post("/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def create_asset(
    body: AssetCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ADMIN)),
) -> AssetOut:
    obj = Asset(**body.model_dump(exclude_unset=True))
    db.add(obj)
    await db.flush()
    return AssetOut.model_validate(obj)


@router.get("/assets", response_model=list[AssetOut])
async def list_assets(
    db: DbSession,
    user: CurrentUser,
    substation_id: Optional[str] = None,
    asset_type: Optional[str] = Query(None),
) -> list[AssetOut]:
    q = select(Asset)
    if substation_id:
        q = q.where(Asset.substation_id == substation_id)
    if asset_type:
        q = q.where(Asset.asset_type == asset_type)
    rows = (await db.execute(q.order_by(Asset.asset_tag))).scalars().all()
    return [AssetOut.model_validate(r) for r in rows]
