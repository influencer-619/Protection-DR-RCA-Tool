"""Cause enrichment — structured field / asset / optional strike evidence for RCA.

Deterministic only: never invent lightning/vegetation from waveforms alone.
Tokens match ``rules/rca/hypotheses.yaml`` required_for_confirmed entries.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# Canonical tokens understood by HypothesisEngine
CAUSE_TOKENS: frozenset[str] = frozenset(
    {
        "lightning_evidence",
        "field_report_vegetation",
        "insulation_evidence",
        "cable_asset_confirmed",
        "switching_event_correlated",
        "external_event_correlated",
        "comm_channel_evidence",
        "intertrip_signal_observed",
    }
)

# Engineer-facing aliases → canonical token
_ALIAS: dict[str, str] = {
    "lightning": "lightning_evidence",
    "lightning_strike": "lightning_evidence",
    "lightning_evidence": "lightning_evidence",
    "vegetation": "field_report_vegetation",
    "tree": "field_report_vegetation",
    "field_report_vegetation": "field_report_vegetation",
    "insulation": "insulation_evidence",
    "flashover": "insulation_evidence",
    "insulation_flashover": "insulation_evidence",
    "insulation_evidence": "insulation_evidence",
    "cable": "cable_asset_confirmed",
    "cable_fault": "cable_asset_confirmed",
    "cable_asset_confirmed": "cable_asset_confirmed",
    "switching": "switching_event_correlated",
    "switching_transient": "switching_event_correlated",
    "switching_event_correlated": "switching_event_correlated",
    "external_grid": "external_event_correlated",
    "external_event": "external_event_correlated",
    "external_event_correlated": "external_event_correlated",
    "comm": "comm_channel_evidence",
    "carrier": "comm_channel_evidence",
    "pilot": "comm_channel_evidence",
    "comm_channel_evidence": "comm_channel_evidence",
    "intertrip": "intertrip_signal_observed",
    "transfer_trip": "intertrip_signal_observed",
    "intertrip_signal_observed": "intertrip_signal_observed",
}

TAG_CHOICES: list[dict[str, str]] = [
    {"token": "lightning_evidence", "label": "Lightning / storm strike evidence"},
    {"token": "field_report_vegetation", "label": "Vegetation / tree contact (field)"},
    {"token": "insulation_evidence", "label": "Insulation flashover evidence"},
    {"token": "cable_asset_confirmed", "label": "Cable asset / UG circuit confirmed"},
    {"token": "switching_event_correlated", "label": "Switching event correlated"},
    {"token": "external_event_correlated", "label": "External grid event correlated"},
    {"token": "comm_channel_evidence", "label": "Pilot / carrier / COMM channel evidence"},
    {"token": "intertrip_signal_observed", "label": "Intertrip / transfer-trip observed"},
]


def canonicalize_token(raw: str) -> Optional[str]:
    key = str(raw or "").strip().lower().replace(" ", "_").replace("-", "_")
    tok = _ALIAS.get(key) or _ALIAS.get(key.upper())
    if tok in CAUSE_TOKENS:
        return tok
    # Accept already-canonical mixed case
    upper = str(raw or "").strip()
    if upper in CAUSE_TOKENS:
        return upper
    return None


def normalize_cause_evidence(raw: Any) -> list[dict[str, Any]]:
    """
    Accept:
      - ["lightning_evidence", "vegetation"]
      - {"tokens": [...], "notes": "..."}
      - [{"token": "...", "source": "ENGINEER", "note": "..."}]
    """
    items: list[dict[str, Any]] = []
    if raw is None:
        return items
    if isinstance(raw, dict) and "tokens" in raw:
        notes = raw.get("notes")
        for t in raw.get("tokens") or []:
            tok = canonicalize_token(str(t))
            if tok:
                items.append({"token": tok, "source": "ENGINEER", "note": notes})
        return _dedupe(items)
    if isinstance(raw, dict) and "items" in raw:
        raw = raw["items"]
    if isinstance(raw, dict):
        # map form {token: true} or {token: note}
        for k, v in raw.items():
            if k in ("notes", "items", "tokens"):
                continue
            tok = canonicalize_token(str(k))
            if not tok:
                continue
            if v is False or v is None:
                continue
            note = v if isinstance(v, str) else None
            items.append({"token": tok, "source": "ENGINEER", "note": note})
        return _dedupe(items)
    if isinstance(raw, (list, tuple)):
        for entry in raw:
            if isinstance(entry, str):
                tok = canonicalize_token(entry)
                if tok:
                    items.append({"token": tok, "source": "ENGINEER", "note": None})
            elif isinstance(entry, dict):
                tok = canonicalize_token(str(entry.get("token") or entry.get("id") or ""))
                if tok:
                    items.append(
                        {
                            "token": tok,
                            "source": str(entry.get("source") or "ENGINEER").upper(),
                            "note": entry.get("note") or entry.get("notes"),
                        }
                    )
    return _dedupe(items)


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for it in items:
        tok = it.get("token")
        if not tok or tok in seen:
            continue
        seen.add(str(tok))
        out.append(it)
    return out


def tokens_from_cause_evidence(raw: Any) -> set[str]:
    return {str(it["token"]) for it in normalize_cause_evidence(raw)}


def tokens_from_asset(asset_type: Optional[str], *, name: Optional[str] = None) -> set[str]:
    """Registry-backed enrichment (no GenAI)."""
    bag: set[str] = set()
    blob = f"{asset_type or ''} {name or ''}".upper()
    if "CABLE" in blob or "UG" in blob or "UNDERGROUND" in blob:
        bag.add("cable_asset_confirmed")
    return bag


def tokens_from_timeline_events(event_types: Iterable[str]) -> set[str]:
    """Map reconstructed digital event types to cause / scheme tokens."""
    types = {str(t) for t in event_types}
    bag: set[str] = set()
    if "communication_signal" in types:
        bag.add("comm_channel_evidence")
    if "intertrip" in types:
        bag.add("intertrip_signal_observed")
    if "reclose" in types:
        bag.add("switching_event_correlated")
    return bag


def match_lightning_csv(
    path: Path | str,
    *,
    event_time: Optional[datetime] = None,
    window_s: float = 300.0,
) -> tuple[bool, dict[str, Any]]:
    """
    Optional strike-file enrichment.

    CSV columns (flexible): time / timestamp / datetime, optional lat/lon.
    Returns (matched, detail). Missing file → (False, limitation).
    """
    p = Path(path)
    if not p.is_file():
        return False, {"status": "NOT_AVAILABLE", "reason": f"Lightning file not found: {p}"}
    if event_time is None:
        return False, {"status": "NOT_AVAILABLE", "reason": "Event time unknown — cannot correlate strikes"}

    et = event_time if event_time.tzinfo else event_time.replace(tzinfo=timezone.utc)
    window = float(window_s)
    hits = 0
    nearest_s: Optional[float] = None
    try:
        with p.open(newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            if not reader.fieldnames:
                return False, {"status": "NOT_AVAILABLE", "reason": "Empty lightning CSV"}
            time_key = None
            for cand in ("time", "timestamp", "datetime", "strike_time", "Time", "Timestamp"):
                if cand in reader.fieldnames:
                    time_key = cand
                    break
            if time_key is None:
                # first column
                time_key = reader.fieldnames[0]
            for row in reader:
                raw_t = (row.get(time_key) or "").strip()
                if not raw_t:
                    continue
                try:
                    st = datetime.fromisoformat(raw_t.replace("Z", "+00:00"))
                except ValueError:
                    continue
                if st.tzinfo is None:
                    st = st.replace(tzinfo=timezone.utc)
                dt = abs((st - et).total_seconds())
                if nearest_s is None or dt < nearest_s:
                    nearest_s = dt
                if dt <= window:
                    hits += 1
    except OSError as exc:
        return False, {"status": "NOT_AVAILABLE", "reason": str(exc)}

    if hits:
        return True, {
            "status": "MATCHED",
            "hits": hits,
            "window_s": window,
            "nearest_delta_s": nearest_s,
        }
    return False, {
        "status": "NO_MATCH",
        "hits": 0,
        "window_s": window,
        "nearest_delta_s": nearest_s,
    }


def collect_enrichment_tokens(
    *,
    cause_evidence: Any = None,
    asset_type: Optional[str] = None,
    asset_name: Optional[str] = None,
    timeline_event_types: Optional[Iterable[str]] = None,
    lightning_csv: Optional[Path | str] = None,
    event_time: Optional[datetime] = None,
    lightning_window_s: float = 300.0,
) -> tuple[set[str], list[str], dict[str, Any]]:
    """Merge all enrichment sources. Returns (tokens, limitations, detail)."""
    bag: set[str] = set()
    limitations: list[str] = []
    detail: dict[str, Any] = {"sources": []}

    eng = tokens_from_cause_evidence(cause_evidence)
    if eng:
        bag |= eng
        detail["sources"].append({"type": "ENGINEER", "tokens": sorted(eng)})

    asset_toks = tokens_from_asset(asset_type, name=asset_name)
    if asset_toks:
        bag |= asset_toks
        detail["sources"].append({"type": "ASSET_REGISTRY", "tokens": sorted(asset_toks)})

    if timeline_event_types is not None:
        tl = tokens_from_timeline_events(timeline_event_types)
        if tl:
            bag |= tl
            detail["sources"].append({"type": "TIMELINE", "tokens": sorted(tl)})

    if lightning_csv:
        ok, info = match_lightning_csv(
            lightning_csv, event_time=event_time, window_s=lightning_window_s
        )
        detail["lightning"] = info
        if ok:
            bag.add("lightning_evidence")
            detail["sources"].append({"type": "LIGHTNING_CSV", "tokens": ["lightning_evidence"]})
        elif info.get("status") == "NOT_AVAILABLE":
            limitations.append(f"Lightning enrichment NOT AVAILABLE — {info.get('reason')}")

    detail["tokens"] = sorted(bag)
    return bag, limitations, detail
