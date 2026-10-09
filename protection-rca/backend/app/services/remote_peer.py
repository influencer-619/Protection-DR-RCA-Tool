"""IED peer linking for line multi-end (87L) and LBB cascade analysis / auto-fetch.

Stored on ``Relay.metadata_json``:

- ``remote_relay_id`` — peer IED id (bidirectional)
- ``peer_type`` — ``none`` | ``line_remote`` | ``cascade``
- ``cascade_role`` — ``INITIATOR`` | ``BACKUP`` (this IED's role when peer_type=cascade)

Optionally mirrored to a linked LINE asset ``parameters.line_ends`` for line peers.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models import Asset, Relay

PEER_TYPE_NONE = "none"
PEER_TYPE_LINE = "line_remote"
PEER_TYPE_CASCADE = "cascade"
PEER_TYPES = frozenset({PEER_TYPE_NONE, PEER_TYPE_LINE, PEER_TYPE_CASCADE})
CASCADE_ROLES = frozenset({"INITIATOR", "BACKUP"})


def _meta(relay: Relay) -> dict[str, Any]:
    return dict(relay.metadata_json) if isinstance(relay.metadata_json, dict) else {}


def get_remote_relay_id(relay: Relay) -> Optional[str]:
    meta = _meta(relay)
    rid = meta.get("remote_relay_id")
    return str(rid) if rid else None


def get_peer_type(relay: Relay) -> str:
    meta = _meta(relay)
    raw = str(meta.get("peer_type") or "").strip().lower()
    if raw in PEER_TYPES and raw != PEER_TYPE_NONE:
        return raw
    # Legacy: remote_relay_id alone → line_remote
    if meta.get("remote_relay_id"):
        return PEER_TYPE_LINE
    return PEER_TYPE_NONE


def get_cascade_role(relay: Relay) -> Optional[str]:
    role = str(_meta(relay).get("cascade_role") or "").strip().upper()
    return role if role in CASCADE_ROLES else None


def peer_end_label_for_local(relay: Relay) -> str:
    """Stamp for this IED's own files when a peer link exists."""
    pt = get_peer_type(relay)
    if pt == PEER_TYPE_CASCADE:
        return get_cascade_role(relay) or "INITIATOR"
    if pt == PEER_TYPE_LINE:
        return "LOCAL"
    return "LOCAL"


def peer_end_label_for_peer(relay: Relay) -> str:
    """Stamp for files fetched/copied from the linked peer into this IED's event."""
    pt = get_peer_type(relay)
    if pt == PEER_TYPE_CASCADE:
        local = get_cascade_role(relay) or "INITIATOR"
        return "BACKUP" if local == "INITIATOR" else "INITIATOR"
    if pt == PEER_TYPE_LINE:
        return "REMOTE"
    return "REMOTE"


def remote_summary(relay: Relay, peer: Optional[Relay]) -> Optional[dict[str, Any]]:
    if peer is None:
        return None
    out: dict[str, Any] = {
        "id": peer.id,
        "name": peer.name,
        "relay_tag": peer.relay_tag,
        "ip_address": peer.ip_address,
        "substation_id": peer.substation_id,
        "peer_type": get_peer_type(relay),
    }
    if get_peer_type(relay) == PEER_TYPE_CASCADE:
        out["cascade_role"] = get_cascade_role(peer)  # peer's role
        out["local_cascade_role"] = get_cascade_role(relay)
    return out


def peer_link_summary(relay: Relay, peer: Optional[Relay]) -> dict[str, Any]:
    """Compact link info for API / UI."""
    pt = get_peer_type(relay)
    return {
        "peer_type": pt,
        "remote_relay_id": get_remote_relay_id(relay),
        "cascade_role": get_cascade_role(relay) if pt == PEER_TYPE_CASCADE else None,
        "peer_end_label": peer_end_label_for_peer(relay) if pt != PEER_TYPE_NONE else None,
        "local_end_label": peer_end_label_for_local(relay) if pt != PEER_TYPE_NONE else "LOCAL",
        "peer": remote_summary(relay, peer) if peer else None,
        "default_analysis_mode": (
            "CASCADE_LBB"
            if pt == PEER_TYPE_CASCADE
            else "LINE_MULTI_END"
            if pt == PEER_TYPE_LINE
            else "NORMAL"
        ),
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


def _clear_peer_fields(relay: Relay) -> None:
    _set_meta(
        relay,
        remote_relay_id=None,
        peer_type=None,
        cascade_role=None,
    )


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


async def set_peer_link(
    db: AsyncSession,
    relay: Relay,
    *,
    peer_type: Optional[str] = None,
    remote_relay_id: Optional[str] = None,
    cascade_role: Optional[str] = None,
) -> Optional[Relay]:
    """Set or clear bidirectional peer link with type.

    Returns the peer Relay (or None if cleared).
    """
    pt = (peer_type or PEER_TYPE_NONE).strip().lower()
    if pt not in PEER_TYPES:
        raise ValueError(f"peer_type must be one of: {', '.join(sorted(PEER_TYPES))}")

    # Clearing
    if pt == PEER_TYPE_NONE or not remote_relay_id:
        old_id = get_remote_relay_id(relay)
        if old_id:
            old = await db.get(Relay, old_id)
            if old is not None and get_remote_relay_id(old) == relay.id:
                _clear_peer_fields(old)
                meta_old = _meta(old)
                if meta_old.get("line_asset_id"):
                    _set_meta(old, line_asset_id=None)
        _clear_peer_fields(relay)
        await _sync_line_asset(db, relay, None)
        _set_meta(relay, line_asset_id=None)
        return None

    if remote_relay_id == relay.id:
        raise ValueError("Peer IED cannot be the same as this IED")

    peer = await db.get(Relay, remote_relay_id)
    if peer is None:
        raise ValueError("Peer IED not found")

    # Clear previous partners on both sides if changed
    old_id = get_remote_relay_id(relay)
    if old_id and old_id != remote_relay_id:
        old = await db.get(Relay, old_id)
        if old is not None and get_remote_relay_id(old) == relay.id:
            _clear_peer_fields(old)

    peer_old = get_remote_relay_id(peer)
    if peer_old and peer_old != relay.id:
        other = await db.get(Relay, peer_old)
        if other is not None and get_remote_relay_id(other) == peer.id:
            _clear_peer_fields(other)

    local_role: Optional[str] = None
    peer_role: Optional[str] = None
    asset_id: Optional[str] = None

    if pt == PEER_TYPE_CASCADE:
        role = (cascade_role or "INITIATOR").strip().upper()
        if role not in CASCADE_ROLES:
            raise ValueError("cascade_role must be INITIATOR or BACKUP")
        local_role = role
        peer_role = "BACKUP" if role == "INITIATOR" else "INITIATOR"
        _set_meta(
            relay,
            remote_relay_id=peer.id,
            peer_type=PEER_TYPE_CASCADE,
            cascade_role=local_role,
            line_asset_id=None,
        )
        _set_meta(
            peer,
            remote_relay_id=relay.id,
            peer_type=PEER_TYPE_CASCADE,
            cascade_role=peer_role,
            line_asset_id=None,
        )
    else:
        # line_remote
        asset_id = await _sync_line_asset(db, relay, peer)
        _set_meta(
            relay,
            remote_relay_id=peer.id,
            peer_type=PEER_TYPE_LINE,
            cascade_role=None,
            line_asset_id=asset_id,
        )
        _set_meta(
            peer,
            remote_relay_id=relay.id,
            peer_type=PEER_TYPE_LINE,
            cascade_role=None,
            line_asset_id=asset_id,
        )
    return peer


async def set_remote_peer(
    db: AsyncSession,
    relay: Relay,
    remote_relay_id: Optional[str],
) -> Optional[Relay]:
    """Backward-compatible: set line remote peer (or clear)."""
    if not remote_relay_id:
        return await set_peer_link(db, relay, peer_type=PEER_TYPE_NONE, remote_relay_id=None)
    return await set_peer_link(
        db,
        relay,
        peer_type=PEER_TYPE_LINE,
        remote_relay_id=remote_relay_id,
    )
