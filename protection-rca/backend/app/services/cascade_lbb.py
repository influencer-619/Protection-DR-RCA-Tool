"""Detect LV→HV (or bay→upstream) LBB / breaker-failure cascade from multi-bay DRs.

Industry pattern (IEEE C37.119-style investigation):
  1) Initiating fault + local trip command
  2) Local breaker fails to open (52a stays closed / current persists)
  3) 50BF / LBB operates and sends intertrip
  4) Upstream / HV bay receives intertrip and clears

Used for a **single event** that holds both initiator and backup COMTRADE packages.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models import Event, EventFile

_BF_RE = re.compile(r"50BF|\bLBB\b|BREAKER.?FAIL|\bBFAIL\b|\bCBF\b|RBRF", re.I)
_TRIP_RE = re.compile(
    r"TRIP|50P|51P.?TRIP|INST.?TRIP|TRIP_CMD|TRIP.?CMD|PROTECTION.?TRIP",
    re.I,
)
_INTERTRIP_SEND_RE = re.compile(
    r"INTERTRIP.?SEND|TT.?SEND|TRANSFER.?TRIP.?SEND|DTT.?SEND|BF.?TX",
    re.I,
)
_INTERTRIP_RX_RE = re.compile(
    r"INTERTRIP.?R(?:ECEIV|X|EC)|INTERTRIP.?RECEIV|TT.?R(?:ECEIV|X)|TRANSFER.?TRIP.?R|"
    r"DTT.?R(?:ECEIV|X)|LBB.?R(?:ECEIV|X)|BF.?RX|BF.?RCV|"
    r"INTERTRIP(?!.*SEND)",
    re.I,
)
_52A_RE = re.compile(r"52A|CB_?52|BREAKER.?STATUS|CB.?STATUS", re.I)


def _digital_names_from_cfg_text(text: str) -> list[str]:
    """Best-effort digital channel names from a COMTRADE CFG (ASCII)."""
    lines = [ln.strip() for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    if len(lines) < 3:
        return []
    # Line 2: TT,Na,Nd
    parts = [p.strip() for p in lines[1].split(",")]
    n_a = n_d = 0
    for tok in parts[1:]:
        t = tok.upper()
        if t.endswith("A") and t[:-1].isdigit():
            n_a = int(t[:-1])
        elif t.endswith("D") and t[:-1].isdigit():
            n_d = int(t[:-1])
    names: list[str] = []
    # Skip station + count + analog lines
    idx = 2 + n_a
    for i in range(n_d):
        if idx + i >= len(lines):
            break
        cols = [c.strip() for c in lines[idx + i].split(",")]
        # Digital: An,ch_id,ph,ccbm,y
        if len(cols) >= 2 and cols[1]:
            names.append(cols[1])
        elif cols:
            names.append(cols[0])
    return names


def scan_cfg_digital_names(paths: list[Path]) -> list[str]:
    out: list[str] = []
    for p in paths:
        if p.suffix.lower() != ".cfg":
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.extend(_digital_names_from_cfg_text(text))
    # unique preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for n in out:
        k = n.upper()
        if k not in seen:
            seen.add(k)
            uniq.append(n)
    return uniq


def scan_soe_tags(paths: list[Path]) -> list[str]:
    tags: list[str] = []
    for p in paths:
        if p.suffix.lower() != ".csv":
            continue
        name_l = p.name.lower()
        if "soe" not in name_l and "event" not in name_l:
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line in text.splitlines()[1:]:
            cols = [c.strip() for c in line.split(",")]
            if len(cols) >= 4:
                tags.append(cols[3])  # Point_Tag
            elif cols:
                tags.append(cols[0])
    return tags


def cascade_time_order(
    timeline_events: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Check initiator BF/trip → intertrip → backup clearance order.

    Each event dict may include ``t_s`` / ``timestamp``, ``event_type``,
    and optional ``end_label`` / ``cascade_role`` (INITIATOR|BACKUP).
    """
    evs = list(timeline_events or [])

    def _t(ev: dict[str, Any]) -> Optional[float]:
        for k in ("t_s", "timestamp", "time_s"):
            if ev.get(k) is not None:
                try:
                    return float(ev[k])
                except (TypeError, ValueError):
                    return None
        return None

    def _role(ev: dict[str, Any]) -> str:
        return str(
            ev.get("cascade_role") or ev.get("end_label") or ev.get("role") or ""
        ).upper()

    init_trip: list[float] = []
    backup_trip: list[float] = []
    intertrip: list[float] = []
    bf_t: list[float] = []
    for ev in evs:
        if not isinstance(ev, dict):
            continue
        t = _t(ev)
        if t is None:
            continue
        et = str(ev.get("event_type") or "").lower()
        role = _role(ev)
        src = str(ev.get("source") or ev.get("channel") or "")
        if et in ("intertrip",) or _INTERTRIP_SEND_RE.search(src) or _INTERTRIP_RX_RE.search(src):
            intertrip.append(t)
        if _BF_RE.search(src) or "bf" in et:
            bf_t.append(t)
        if et in ("protection_trip", "breaker_trip_command"):
            if role in ("BACKUP", "REMOTE", "HV"):
                backup_trip.append(t)
            elif role in ("INITIATOR", "LOCAL", "LV"):
                init_trip.append(t)
            else:
                init_trip.append(t)

    if not init_trip and not backup_trip:
        return {
            "status": "NOT_CALCULABLE",
            "order_ok": None,
            "notes": "Need timed trip/BF/intertrip events to verify cascade order",
        }

    t_init = min(init_trip + bf_t) if (init_trip or bf_t) else None
    t_it = min(intertrip) if intertrip else None
    t_bak = min(backup_trip) if backup_trip else None

    order_ok = True
    notes: list[str] = []
    if t_init is not None and t_bak is not None and t_bak + 1e-6 < t_init:
        order_ok = False
        notes.append("Backup trip earlier than initiator — order inconsistent")
    if t_init is not None and t_it is not None and t_it + 1e-6 < t_init:
        order_ok = False
        notes.append("Intertrip earlier than initiator trip/BF")
    if t_it is not None and t_bak is not None and t_bak + 1e-6 < t_it:
        # Backup can align with RX; small early skew OK within 20 ms
        if t_it - t_bak > 0.020:
            order_ok = False
            notes.append("Backup clearance much earlier than intertrip")
    if order_ok:
        notes.append("Cascade time order consistent (initiator → intertrip → backup)")

    return {
        "status": "OK",
        "order_ok": order_ok,
        "t_initiator_s": t_init,
        "t_intertrip_s": t_it,
        "t_backup_s": t_bak,
        "notes": "; ".join(notes),
    }


def classify_intertrip_direction(
    *,
    digital_names: Optional[list[str]] = None,
    soe_tags: Optional[list[str]] = None,
    timeline_events: Optional[list[Any]] = None,
) -> dict[str, bool]:
    """Classify intertrip SEND vs RECEIVE for *this* bay.

    Prefer COMTRADE digital channel names on the local DR. Station SOE often
    contains both LV SEND and HV RECEIVE; those must not cancel a local RX.
    Timeline point_tag / signal / channel text is used as a secondary source.
    """
    local = [str(n) for n in (digital_names or []) if n]
    soe = [str(n) for n in (soe_tags or []) if n]
    tl_names: list[str] = []
    for ev in timeline_events or []:
        if isinstance(ev, dict):
            src = str(ev.get("source") or "")
            meta = ev.get("metadata") if isinstance(ev.get("metadata"), dict) else {}
            et = str(ev.get("event_type") or "")
        else:
            src = str(getattr(ev, "source", "") or "")
            meta = getattr(ev, "metadata", None)
            if not isinstance(meta, dict):
                meta = {}
            et = str(getattr(ev, "event_type", "") or "")
        for raw in (
            src,
            meta.get("point_tag"),
            meta.get("signal"),
            meta.get("channel"),
            meta.get("label"),
        ):
            if raw:
                tl_names.append(str(raw))
        if et and "intertrip" in et.lower():
            tl_names.append(et)

    local_send = any(_INTERTRIP_SEND_RE.search(n) for n in local)
    local_rx = any(_INTERTRIP_RX_RE.search(n) for n in local)
    # Timeline / SOE only fill gaps when local CFG has no intertrip channels
    aux = soe + tl_names
    aux_send = any(_INTERTRIP_SEND_RE.search(n) for n in aux)
    aux_rx = any(_INTERTRIP_RX_RE.search(n) for n in aux)

    if local_send or local_rx:
        # Local DR digitals define the bay role
        has_send = local_send
        has_rx = local_rx
        # Allow aux RX alongside local send only when local also has RX (dual)
        if local_rx and not local_send and aux_send:
            # Station SOE SEND from initiator — do not flip this bay to sender
            has_send = False
    else:
        has_send = aux_send
        has_rx = aux_rx
        # If both appear only in station SOE, prefer RX when RECEIVED/RX wording
        # is present (backup clearance is the actionable story on HV DRs).
        if has_send and has_rx:
            rx_strong = any(
                re.search(r"RECEIV|INTERTRIP_RX|\bTT_?RX\b|\bBF_?RX\b", n, re.I)
                for n in aux
            )
            if rx_strong:
                has_send = False

    return {
        "intertrip_send_seen": bool(has_send),
        "intertrip_receive_seen": bool(has_rx),
        "cascade_upstream_clearance": bool(has_rx and not has_send),
    }


def detect_lbb_cascade(
    *,
    digital_names: list[str],
    soe_tags: Optional[list[str]] = None,
    cascade_mode: bool = False,
    timeline_events: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Return cascade evidence tokens for RCA / Summary."""
    names = list(digital_names or []) + list(soe_tags or [])
    has_bf = any(_BF_RE.search(n) for n in names)
    has_trip = any(_TRIP_RE.search(n) for n in names)
    direction = classify_intertrip_direction(
        digital_names=digital_names,
        soe_tags=soe_tags,
        timeline_events=timeline_events,
    )
    has_it_send = direction["intertrip_send_seen"]
    has_it_rx = direction["intertrip_receive_seen"]
    has_52a = any(_52A_RE.search(n) for n in names)

    # Strong cascade: BF/LBB + intertrip path (send and/or receive)
    cascade = bool(
        has_bf
        and (has_it_send or has_it_rx)
        and (has_trip or cascade_mode)
    )
    # Softer: user marked cascade upload + BF or intertrip both ends
    if cascade_mode and has_bf and (has_it_send or has_it_rx):
        cascade = True
    if cascade_mode and has_it_send and has_it_rx and has_trip:
        cascade = True

    order = cascade_time_order(timeline_events)
    if cascade and order.get("order_ok") is False:
        # Downgrade name-only cascade when timeline order contradicts
        if not cascade_mode:
            cascade = False

    return {
        "cascade_lbb_detected": cascade,
        "bf_element_seen": has_bf,
        "trip_element_seen": has_trip,
        "intertrip_send_seen": has_it_send,
        "intertrip_receive_seen": has_it_rx,
        "cascade_upstream_clearance": bool(direction.get("cascade_upstream_clearance")),
        "breaker_status_seen": has_52a,
        "digital_names_scanned": len(digital_names or []),
        "time_order": order,
        "notes": (
            "LBB cascade pattern: local BF/LBB with intertrip to upstream clearance"
            if cascade
            else (
                "Upstream intertrip receive (backup clearance) — no local BF cascade root"
                if direction.get("cascade_upstream_clearance")
                else "No LBB multi-bay cascade pattern from digitals/SOE"
            )
        ),
    }


async def enrich_event_cascade(
    db: AsyncSession,
    event: Event,
    *,
    file_paths: list[Path],
    digital_channel_names: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Scan event files, persist cascade block on event.extra, return flags for pipeline."""
    cfg_names = scan_cfg_digital_names(file_paths)
    soe_tags = scan_soe_tags(file_paths)
    merged = list(digital_channel_names or []) + cfg_names

    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    cascade_meta = dict(extra.get("cascade") or {})
    cascade_mode = str(cascade_meta.get("mode") or "").upper() in (
        "LBB_MULTI_BAY",
        "CASCADE",
        "LBB",
    )

    # Infer cascade mode from INITIATOR/BACKUP end labels on files
    rows = (
        await db.execute(select(EventFile).where(EventFile.event_id == event.id))
    ).scalars().all()
    labels = set()
    for ef in rows:
        meta = ef.file_metadata if isinstance(ef.file_metadata, dict) else {}
        lab = str(meta.get("end_label") or "").upper()
        if lab:
            labels.add(lab)
        role = str(meta.get("cascade_role") or "").upper()
        if role:
            labels.add(role)
    if labels & {"INITIATOR", "BACKUP"} or (
        "LOCAL" in labels and "REMOTE" in labels and cascade_mode
    ):
        cascade_mode = True
        cascade_meta.setdefault("mode", "LBB_MULTI_BAY")

    det = detect_lbb_cascade(
        digital_names=merged,
        soe_tags=soe_tags,
        cascade_mode=cascade_mode,
    )
    cascade_meta.update(
        {
            "detected": det["cascade_lbb_detected"],
            "pattern": "LV_BF_TO_HV_INTERTRIP" if det["cascade_lbb_detected"] else None,
            "bf_element_seen": det["bf_element_seen"],
            "intertrip_send_seen": det["intertrip_send_seen"],
            "intertrip_receive_seen": det["intertrip_receive_seen"],
            "time_order": det.get("time_order"),
            "notes": det["notes"],
        }
    )
    extra["cascade"] = cascade_meta
    event.extra = extra

    flags: dict[str, Any] = {
        "cascade_lbb_detected": det["cascade_lbb_detected"],
        "digital_channel_names": merged,
        "intertrip_send_seen": det["intertrip_send_seen"],
        "intertrip_receive_seen": det["intertrip_receive_seen"],
    }
    if det["bf_element_seen"]:
        # Present BF channel — logic satisfaction needs persist / cascade mode
        flags["scheme_tokens"] = ["scheme_breaker_failure"]
    if det["intertrip_send_seen"] or det["intertrip_receive_seen"]:
        flags["intertrip"] = True
    # Backup / upstream bay: received intertrip (not local BF root cause)
    if det.get("cascade_upstream_clearance") or (
        det["intertrip_receive_seen"] and not det["intertrip_send_seen"]
    ):
        flags["cascade_upstream_clearance"] = True
        flags["intertrip_receive_seen"] = True
    if det["cascade_lbb_detected"] and det["bf_element_seen"]:
        flags["trip_command"] = True
        # Invent persist only for explicit Combined Cascade mode (user-selected
        # initiator+backup). Opportunistic CFG name matches must not force BF.
        if cascade_mode and not flags.get("cascade_upstream_clearance"):
            flags["current_persists"] = True
            flags["persist_evidence"] = "cascade_mode"
            flags["scheme_tokens"] = [
                "scheme_breaker_failure",
                "bf_logic_satisfied",
            ]
    return flags
