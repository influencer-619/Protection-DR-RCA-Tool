"""Opposite-end IED pairing for multi-end (87L) manual upload and auto-fetch.

Stored on ``Relay.metadata_json["remote_relay_id"]`` (bidirectional). Optionally
mirrored to a linked LINE asset ``parameters.line_ends``.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, Relay


def _meta(relay: Relay) -> dict[str, Any]:
    return dict(relay.metadata_json) if isinstance(relay.metadata_json, dict) else {}


def get_remote_relay_id(relay: Relay) -> Optional[str]:
    meta = _meta(relay)
    rid = meta.get("remote_relay_id")
    if rid:
        return str(rid)
    # Fall back to LINE asset ends if present
    line_asset_id = meta.get("line_asset_id")
    if not line_asset_id:
        return None
    return None  # resolved async via resolve_remote_relay when asset loaded


def remote_summary(relay: Relay, peer: Optional[Relay]) -> Optional[dict[str, Any]]:
    if peer is None:
        return None
    return {
        "id": peer.id,
        "name": peer.name,
        "relay_tag": peer.relay_tag,
        "ip_address": peer.ip_address,
        "substation_id": peer.substation_id,
    }


async def resolve_remote_relay(db: AsyncSession, relay: Relay) -> Optional[Relay]:
    """Return the peer IED for ``relay``, or None if unpaired / missing."""
    meta = _meta(relay)
    rid = meta.get("remote_relay_id")
    if rid:
        peer = await db.get(Relay, str(rid))
        if peer is not None and peer.id != relay.id:
            return peer
    line_asset_id = meta.get("line_asset_id")
    if line_asset_id:
        asset = await db.get(Asset, str(line_asset_id))
        if asset is not None and isinstance(asset.parameters, dict):
            ends = asset.parameters.get("line_ends") or []
            if isinstance(ends, list):
                for end in ends:
                    if not isinstance(end, dict):
                        continue
                    other = end.get("relay_id")
                    if other and str(other) != relay.id:
                        peer = await db.get(Relay, str(other))
                        if peer is not None:
                            return peer
    # Asset scan: LINE assets that list this relay in line_ends
    rows = (
        await db.execute(select(Asset).where(Asset.asset_type == "LINE", Asset.is_active.is_(True)))
    ).scalars().all()
    for asset in rows:
        params = asset.parameters if isinstance(asset.parameters, dict) else {}
        ends = params.get("line_ends") or []
        if not isinstance(ends, list):
            continue
        ids = [
            str(e.get("relay_id"))
            for e in ends
            if isinstance(e, dict) and e.get("relay_id")
        ]
        if relay.id not in ids:
            continue
        for other_id in ids:
            if other_id != relay.id:
                peer = await db.get(Relay, other_id)
                if peer is not None:
                    return peer
    return None


def _set_meta(relay: Relay, **updates: Any) -> None:
    meta = _meta(relay)
    for k, v in updates.items():
        if v is None:
            meta.pop(k, None)
        else:
            meta[k] = v
    relay.metadata_json = meta
    flag_modified(relay, "metadata_json")


async def _sync_line_asset(
    db: AsyncSession,
    relay_a: Relay,
    relay_b: Optional[Relay],
) -> Optional[str]:
    """Keep a simple LINE asset line_ends in sync; return asset id if any."""
    meta_a = _meta(relay_a)
    asset_id = meta_a.get("line_asset_id")
    asset: Optional[Asset] = None
    if asset_id:
        asset = await db.get(Asset, str(asset_id))
    if relay_b is None:
        if asset is not None and isinstance(asset.parameters, dict):
            params = dict(asset.parameters)
            params.pop("line_ends", None)
            asset.parameters = params
            flag_modified(asset, "parameters")
        return str(asset_id) if asset_id else None

    ends = [
        {
            "role": "END_A",
            "relay_id": relay_a.id,
            "label": relay_a.name or relay_a.relay_tag,
        },
        {
            "role": "END_B",
            "relay_id": relay_b.id,
            "label": relay_b.name or relay_b.relay_tag,
        },
    ]
    if asset is None:
        tag = f"LINE-{relay_a.relay_tag}-{relay_b.relay_tag}"[:120]
        asset = Asset(
            asset_tag=tag,
            name=f"{relay_a.name} ↔ {relay_b.name}",
            asset_type="LINE",
            substation_id=relay_a.substation_id,
            bay_id=relay_a.bay_id,
            parameters={"line_ends": ends},
            is_active=True,
        )
        db.add(asset)
        await db.flush()
    else:
        params = dict(asset.parameters) if isinstance(asset.parameters, dict) else {}
        params["line_ends"] = ends
        asset.parameters = params
        flag_modified(asset, "parameters")
    return asset.id


async def set_remote_peer(
    db: AsyncSession,
    relay: Relay,
    remote_relay_id: Optional[str],
) -> Optional[Relay]:
    """Set or clear bidirectional remote peer. Returns the peer (or None if cleared)."""
    # Clear previous peer link on both sides
    old_id = get_remote_relay_id(relay)
    if old_id and old_id != remote_relay_id:
        old = await db.get(Relay, old_id)
        if old is not None and get_remote_relay_id(old) == relay.id:
            _set_meta(old, remote_relay_id=None)

    if not remote_relay_id:
        _set_meta(relay, remote_relay_id=None)
        await _sync_line_asset(db, relay, None)
        return None

    if remote_relay_id == relay.id:
        raise ValueError("Remote IED cannot be the same as this IED")

    peer = await db.get(Relay, remote_relay_id)
    if peer is None:
        raise ValueError("Remote IED not found")

    # If peer already paired to someone else, clear that link
    peer_old = get_remote_relay_id(peer)
    if peer_old and peer_old != relay.id:
        other = await db.get(Relay, peer_old)
        if other is not None and get_remote_relay_id(other) == peer.id:
            _set_meta(other, remote_relay_id=None)

    asset_id = await _sync_line_asset(db, relay, peer)
    _set_meta(relay, remote_relay_id=peer.id, line_asset_id=asset_id)
    _set_meta(peer, remote_relay_id=relay.id, line_asset_id=asset_id)
    return peer
