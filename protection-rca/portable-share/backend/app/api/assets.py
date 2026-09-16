"""Plant hierarchy API — Substation → Voltage Level → Bay → Feeder → IED."""

from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import (
    Asset,
    Bay,
    Breaker,
    Event,
    Feeder,
    Relay,
    Substation,
    VoltageLevel,
)
from app.models import User
from app.schemas.assets import (
    AssetCreate,
    AssetOut,
    BayCreate,
    BayOut,
    BreakerCreate,
    BreakerOut,
    FeederCreate,
    FeederOut,
    IedContextOut,
    PlantBayNode,
    PlantFeederNode,
    PlantIedNode,
    PlantSubstationNode,
    PlantTreeOut,
    PlantVoltageLevelNode,
    RelayCreate,
    RelayOut,
    SubstationCreate,
    SubstationOut,
    VoltageLevelCreate,
    VoltageLevelOut,
)

router = APIRouter(prefix="/api", tags=["plant"])


def _slug_code(name: str, *, max_len: int = 64) -> str:
    raw = re.sub(r"[^A-Za-z0-9]+", "-", (name or "").strip()).strip("-").upper()
    return (raw or "ITEM")[:max_len]


# --- Substations ---


@router.post("/substations", response_model=SubstationOut, status_code=status.HTTP_201_CREATED)
async def create_substation(
    body: SubstationCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> SubstationOut:
    data = body.model_dump(exclude_unset=True)
    if not data.get("code"):
        data["code"] = _slug_code(body.name)
    # Ensure unique code
    base = data["code"]
    n = 1
    while (
        await db.execute(select(Substation.id).where(Substation.code == data["code"]))
    ).scalar_one_or_none():
        n += 1
        data["code"] = f"{base}-{n}"[:64]
    obj = Substation(**data)
    db.add(obj)
    await db.flush()
    return SubstationOut.model_validate(obj)


@router.get("/substations", response_model=list[SubstationOut])
async def list_substations(db: DbSession, user: CurrentUser) -> list[SubstationOut]:
    rows = (await db.execute(select(Substation).order_by(Substation.name))).scalars().all()
    return [SubstationOut.model_validate(r) for r in rows]


@router.get("/substations/{substation_id}", response_model=SubstationOut)
async def get_substation(
    substation_id: str, db: DbSession, user: CurrentUser
) -> SubstationOut:
    row = await db.get(Substation, substation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Substation not found")
    return SubstationOut.model_validate(row)


@router.delete("/substations/{substation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_substation(
    substation_id: str,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> None:
    row = await db.get(Substation, substation_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Substation not found")
    await db.delete(row)
    await db.flush()


# --- Voltage levels ---


@router.post(
    "/voltage-levels",
    response_model=VoltageLevelOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_voltage_level(
    body: VoltageLevelCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> VoltageLevelOut:
    sub = await db.get(Substation, body.substation_id)
    if sub is None:
        raise HTTPException(status_code=404, detail="Substation not found")
    code = body.code or _slug_code(
        body.name if not body.nominal_voltage_kv else f"{body.nominal_voltage_kv}kV"
    )
    obj = VoltageLevel(
        substation_id=body.substation_id,
        name=body.name.strip(),
        code=code,
        nominal_voltage_kv=body.nominal_voltage_kv,
    )
    db.add(obj)
    await db.flush()
    return VoltageLevelOut.model_validate(obj)


@router.get("/voltage-levels", response_model=list[VoltageLevelOut])
async def list_voltage_levels(
    db: DbSession,
    user: CurrentUser,
    substation_id: Optional[str] = None,
) -> list[VoltageLevelOut]:
    q = select(VoltageLevel)
    if substation_id:
        q = q.where(VoltageLevel.substation_id == substation_id)
    rows = (await db.execute(q.order_by(VoltageLevel.name))).scalars().all()
    return [VoltageLevelOut.model_validate(r) for r in rows]


@router.delete("/voltage-levels/{voltage_level_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_voltage_level(
    voltage_level_id: str,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> None:
    row = await db.get(VoltageLevel, voltage_level_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Voltage level not found")
    await db.delete(row)
    await db.flush()


# --- Bays ---


@router.post("/bays", response_model=BayOut, status_code=status.HTTP_201_CREATED)
async def create_bay(
    body: BayCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> BayOut:
    vl = await db.get(VoltageLevel, body.voltage_level_id)
    if vl is None:
        raise HTTPException(status_code=404, detail="Voltage level not found")
    name = body.name.strip()
    code = body.code or _slug_code(name)
    obj = Bay(
        substation_id=vl.substation_id,
        voltage_level_id=vl.id,
        name=name,
        code=code,
        bay_type=body.bay_type,
        voltage_kv=body.voltage_kv if body.voltage_kv is not None else vl.nominal_voltage_kv,
        feeder_name=body.feeder_name,
    )
    db.add(obj)
    await db.flush()
    return BayOut.model_validate(obj)


@router.get("/bays", response_model=list[BayOut])
async def list_bays(
    db: DbSession,
    user: CurrentUser,
    substation_id: Optional[str] = None,
    voltage_level_id: Optional[str] = None,
) -> list[BayOut]:
    q = select(Bay)
    if substation_id:
        q = q.where(Bay.substation_id == substation_id)
    if voltage_level_id:
        q = q.where(Bay.voltage_level_id == voltage_level_id)
    rows = (await db.execute(q.order_by(Bay.name))).scalars().all()
    return [BayOut.model_validate(r) for r in rows]


@router.delete("/bays/{bay_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bay(
    bay_id: str,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> None:
    row = await db.get(Bay, bay_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Bay not found")
    await db.delete(row)
    await db.flush()


# --- Feeders ---


@router.post("/feeders", response_model=FeederOut, status_code=status.HTTP_201_CREATED)
async def create_feeder(
    body: FeederCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> FeederOut:
    bay = await db.get(Bay, body.bay_id)
    if bay is None:
        raise HTTPException(status_code=404, detail="Bay not found")
    name = body.name.strip()
    obj = Feeder(bay_id=bay.id, name=name, code=body.code or _slug_code(name))
    db.add(obj)
    await db.flush()
    return FeederOut.model_validate(obj)


@router.get("/feeders", response_model=list[FeederOut])
async def list_feeders(
    db: DbSession,
    user: CurrentUser,
    bay_id: Optional[str] = None,
) -> list[FeederOut]:
    q = select(Feeder)
    if bay_id:
        q = q.where(Feeder.bay_id == bay_id)
    rows = (await db.execute(q.order_by(Feeder.name))).scalars().all()
    return [FeederOut.model_validate(r) for r in rows]


@router.delete("/feeders/{feeder_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feeder(
    feeder_id: str,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> None:
    row = await db.get(Feeder, feeder_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Feeder not found")
    await db.delete(row)
    await db.flush()


# --- IEDs (relays) ---


@router.post("/ieds", response_model=RelayOut, status_code=status.HTTP_201_CREATED)
@router.post("/relays", response_model=RelayOut, status_code=status.HTTP_201_CREATED)
async def create_ied(
    body: RelayCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> RelayOut:
    feeder = await db.get(Feeder, body.feeder_id)
    if feeder is None:
        raise HTTPException(status_code=404, detail="Feeder not found")
    bay = await db.get(Bay, feeder.bay_id)
    if bay is None:
        raise HTTPException(status_code=404, detail="Bay not found")
    name = body.name.strip()
    tag = (body.relay_tag or _slug_code(name, max_len=128)).strip()
    obj = Relay(
        feeder_id=feeder.id,
        bay_id=bay.id,
        substation_id=bay.substation_id,
        name=name,
        relay_tag=tag,
        manufacturer=body.manufacturer,
        model=body.model,
        firmware_version=body.firmware_version,
        protection_functions=body.protection_functions,
    )
    db.add(obj)
    await db.flush()
    return RelayOut.model_validate(obj)


@router.get("/ieds", response_model=list[RelayOut])
@router.get("/relays", response_model=list[RelayOut])
async def list_ieds(
    db: DbSession,
    user: CurrentUser,
    substation_id: Optional[str] = None,
    bay_id: Optional[str] = None,
    feeder_id: Optional[str] = None,
) -> list[RelayOut]:
    q = select(Relay)
    if substation_id:
        q = q.where(Relay.substation_id == substation_id)
    if bay_id:
        q = q.where(Relay.bay_id == bay_id)
    if feeder_id:
        q = q.where(Relay.feeder_id == feeder_id)
    rows = (await db.execute(q.order_by(Relay.relay_tag))).scalars().all()
    return [RelayOut.model_validate(r) for r in rows]


@router.get("/ieds/{ied_id}", response_model=IedContextOut)
async def get_ied_context(
    ied_id: str, db: DbSession, user: CurrentUser
) -> IedContextOut:
    row = await db.get(Relay, ied_id)
    if row is None:
        raise HTTPException(status_code=404, detail="IED not found")
    if not row.feeder_id:
        raise HTTPException(
            status_code=400,
            detail="IED is not linked to a feeder — map it under Plant first",
        )
    feeder = await db.get(Feeder, row.feeder_id)
    bay = await db.get(Bay, feeder.bay_id) if feeder else None
    if feeder is None or bay is None:
        raise HTTPException(status_code=400, detail="IED plant path incomplete")
    vl = (
        await db.get(VoltageLevel, bay.voltage_level_id)
        if bay.voltage_level_id
        else None
    )
    sub = await db.get(Substation, bay.substation_id)
    if sub is None:
        raise HTTPException(status_code=400, detail="Substation missing for IED")
    parts = [sub.name]
    if vl:
        parts.append(vl.name)
    parts.extend([bay.name, feeder.name, row.name])
    return IedContextOut(
        ied=RelayOut.model_validate(row),
        feeder=FeederOut.model_validate(feeder),
        bay=BayOut.model_validate(bay),
        voltage_level=VoltageLevelOut.model_validate(vl) if vl else None,
        substation=SubstationOut.model_validate(sub),
        path_label=" / ".join(parts),
    )


@router.get("/relays/{relay_id}", response_model=RelayOut)
async def get_relay(relay_id: str, db: DbSession, user: CurrentUser) -> RelayOut:
    row = await db.get(Relay, relay_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Relay not found")
    return RelayOut.model_validate(row)


@router.delete("/ieds/{ied_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ied(
    ied_id: str,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> None:
    row = await db.get(Relay, ied_id)
    if row is None:
        raise HTTPException(status_code=404, detail="IED not found")
    await db.delete(row)
    await db.flush()


# --- Plant tree ---


@router.get("/plant/tree", response_model=PlantTreeOut)
async def get_plant_tree(db: DbSession, user: CurrentUser) -> PlantTreeOut:
    subs = (
        await db.execute(
            select(Substation)
            .options(
                selectinload(Substation.voltage_levels)
                .selectinload(VoltageLevel.bays)
                .selectinload(Bay.feeders)
                .selectinload(Feeder.ieds)
            )
            .order_by(Substation.name)
        )
    ).scalars().all()

    # Event counts per relay
    count_rows = (
        await db.execute(
            select(Event.relay_id, func.count())
            .where(Event.relay_id.is_not(None))
            .group_by(Event.relay_id)
        )
    ).all()
    counts = {rid: int(c) for rid, c in count_rows if rid}

    out_subs: list[PlantSubstationNode] = []
    for sub in subs:
        vl_nodes: list[PlantVoltageLevelNode] = []
        for vl in sorted(sub.voltage_levels, key=lambda x: x.name or ""):
            bay_nodes: list[PlantBayNode] = []
            for bay in sorted(vl.bays, key=lambda x: x.name or ""):
                feeder_nodes: list[PlantFeederNode] = []
                for feeder in sorted(bay.feeders, key=lambda x: x.name or ""):
                    ied_nodes = [
                        PlantIedNode(
                            id=ied.id,
                            name=ied.name,
                            relay_tag=ied.relay_tag,
                            feeder_id=ied.feeder_id,
                            event_count=counts.get(ied.id, 0),
                        )
                        for ied in sorted(feeder.ieds, key=lambda x: x.name or "")
                    ]
                    feeder_nodes.append(
                        PlantFeederNode(
                            id=feeder.id,
                            name=feeder.name,
                            code=feeder.code,
                            ieds=ied_nodes,
                        )
                    )
                bay_nodes.append(
                    PlantBayNode(
                        id=bay.id,
                        name=bay.name,
                        code=bay.code,
                        voltage_level_id=bay.voltage_level_id,
                        feeders=feeder_nodes,
                    )
                )
            vl_nodes.append(
                PlantVoltageLevelNode(
                    id=vl.id,
                    name=vl.name,
                    code=vl.code,
                    nominal_voltage_kv=vl.nominal_voltage_kv,
                    bays=bay_nodes,
                )
            )
        out_subs.append(
            PlantSubstationNode(
                id=sub.id,
                name=sub.name,
                code=sub.code,
                voltage_levels=vl_nodes,
            )
        )
    return PlantTreeOut(substations=out_subs)


# --- Breakers / Assets (legacy kept) ---


@router.post("/breakers", response_model=BreakerOut, status_code=status.HTTP_201_CREATED)
async def create_breaker(
    body: BreakerCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
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


@router.post("/assets", response_model=AssetOut, status_code=status.HTTP_201_CREATED)
async def create_asset(
    body: AssetCreate,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
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
