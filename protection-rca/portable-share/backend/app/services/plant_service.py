"""Plant path helpers — resolve IED → labels / FKs for events."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bay, Feeder, Relay, Substation, VoltageLevel


async def resolve_ied_plant(
    db: AsyncSession, relay_id: str
) -> dict[str, Any]:
    """Return FKs + display labels for binding an event to an IED."""
    relay = await db.get(Relay, relay_id)
    if relay is None:
        raise HTTPException(status_code=404, detail="IED not found")
    if not relay.feeder_id:
        raise HTTPException(
            status_code=400,
            detail="IED must belong to a feeder in the plant tree",
        )
    feeder = await db.get(Feeder, relay.feeder_id)
    if feeder is None:
        raise HTTPException(status_code=400, detail="Feeder missing for IED")
    bay = await db.get(Bay, feeder.bay_id)
    if bay is None:
        raise HTTPException(status_code=400, detail="Bay missing for IED")
    vl: Optional[VoltageLevel] = None
    if bay.voltage_level_id:
        vl = await db.get(VoltageLevel, bay.voltage_level_id)
    sub = await db.get(Substation, bay.substation_id)
    if sub is None:
        raise HTTPException(status_code=400, detail="Substation missing for IED")

    return {
        "relay_id": relay.id,
        "bay_id": bay.id,
        "substation_id": sub.id,
        "feeder": feeder.name,
        "nominal_voltage_kv": (
            vl.nominal_voltage_kv
            if vl and vl.nominal_voltage_kv is not None
            else bay.voltage_kv
        ),
        "labels": {
            "substation_name": sub.name,
            "bay_name": bay.name,
            "relay_tag": relay.relay_tag or relay.name,
            "asset_name": feeder.name,
            "voltage_level_name": vl.name if vl else None,
            "feeder_name": feeder.name,
            "ied_name": relay.name,
        },
    }
