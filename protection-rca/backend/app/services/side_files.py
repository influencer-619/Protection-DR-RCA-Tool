"""Load SOE CSV and relay event-report text into timeline contributions.

Never invents events — only parses what is present in uploaded side files.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from event_reconstruction.timeline import TimelineEvent

logger = logging.getLogger(__name__)

_SIGNAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"INCEPTION|FAULT\s*START|FAULT\s*INCEPT", re.I), "fault_inception"),
    (re.compile(r"PICK\s*UP|PICKUP|_PU\b|Z\d.*PU", re.I), "protection_pickup"),
    (re.compile(r"TRIP|_TR\b|OPERATE|Z\d.*TRIP", re.I), "protection_trip"),
    (re.compile(r"52A|52_A|BREAKER.*OPEN|CB\s*OPEN|52A_CLOSED", re.I), "52a_change"),
    (re.compile(r"52B|52_B", re.I), "52b_change"),
    (re.compile(r"RECLOSE|79\b", re.I), "reclose"),
    (re.compile(r"LOCKOUT|86\b", re.I), "lockout"),
    (re.compile(r"INTERTRIP|TRANSFER", re.I), "intertrip"),
    (re.compile(r"50BF|BREAKER.?FAIL", re.I), "breaker_trip_command"),
]

_REPORT_LINE = re.compile(
    r"^(?P<label>.+?):\s*(?P<t>[\d.]+)\s*s\s*$",
    re.I,
)


def _classify_signal(name: str) -> str:
    for pat, etype in _SIGNAL_PATTERNS:
        if pat.search(name or ""):
            return etype
    return "external_signal"


def _parse_ts(raw: str) -> Optional[datetime]:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _element_from_label(label: str) -> Optional[str]:
    m = re.search(
        r"\b(87RGF|50BF|87G|87T|87L|87B|50N|51N|67N|67P|50P|51P|21G|21P|32R|81U|81O|81R|50|51|21|67|87|32|46|68|78|79|86|25|27|59)\b",
        label or "",
        re.I,
    )
    return m.group(1).upper() if m else None


def parse_soe_csv(
    text: str,
    *,
    source_name: str = "soe.csv",
    t0: Optional[datetime] = None,
) -> list[TimelineEvent]:
    """Parse SOE CSV (timestamp_utc,signal,value,source) → TimelineEvent list."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    # Normalize headers
    fields = { (h or "").strip().lower(): h for h in reader.fieldnames }
    ts_key = fields.get("timestamp_utc") or fields.get("timestamp") or fields.get("time")
    sig_key = fields.get("signal") or fields.get("event") or fields.get("point")
    val_key = fields.get("value") or fields.get("state")
    src_key = fields.get("source") or fields.get("device")
    if not ts_key or not sig_key:
        logger.warning("SOE CSV %s missing timestamp/signal columns", source_name)
        return []

    rows: list[tuple[datetime, str, str, Any]] = []
    for row in reader:
        dt = _parse_ts(str(row.get(ts_key) or ""))
        sig = str(row.get(sig_key) or "").strip()
        if dt is None or not sig:
            continue
        val = row.get(val_key) if val_key else None
        src = str(row.get(src_key) or source_name)
        rows.append((dt, sig, src, val))
    if not rows:
        return []

    rows.sort(key=lambda r: r[0])
    if t0 is None:
        # Align to whole second of first event so .410 → 0.410 s (package convention)
        first = rows[0][0]
        t0 = first.replace(microsecond=0)

    out: list[TimelineEvent] = []
    for dt, sig, src, val in rows:
        # Skip de-assert / zero unless useful
        try:
            if val is not None and float(val) == 0 and "CLOSED" not in sig.upper():
                # 52A_CLOSED,0 means breaker opened — keep
                if "52A" not in sig.upper() and "52B" not in sig.upper():
                    continue
        except (TypeError, ValueError):
            pass
        etype = _classify_signal(sig)
        if "52A" in sig.upper() and str(val) in ("0", "0.0"):
            etype = "52a_change"
        rel = (dt - t0).total_seconds()
        if rel < -1:
            continue
        out.append(
            TimelineEvent(
                event_type=etype,
                timestamp=float(rel),
                source=f"SOE:{src}",
                confidence="HIGH",
                evidence_ids=[f"soe:{source_name}:{sig}"],
                metadata={
                    "signal": sig,
                    "value": val,
                    "absolute_time": dt.isoformat(),
                    "element": _element_from_label(sig),
                    "file": source_name,
                },
            )
        )
    return out


def parse_relay_event_report(
    text: str,
    *,
    source_name: str = "relay_event_report.txt",
) -> list[TimelineEvent]:
    """Parse simple relay event report lines like '21 Z1 pickup: 0.410 s'."""
    out: list[TimelineEvent] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("=") or line.upper().startswith("PROTECTION"):
            continue
        m = _REPORT_LINE.match(line)
        if not m:
            # Also accept "Fault: A-G" style without time — skip
            continue
        label = m.group("label").strip()
        try:
            t = float(m.group("t"))
        except ValueError:
            continue
        etype = _classify_signal(label)
        if "inception" in label.lower() or label.lower().startswith("fault inception"):
            etype = "fault_inception"
        if "open" in label.lower() and "52" in label:
            etype = "52a_change"
        out.append(
            TimelineEvent(
                event_type=etype,
                timestamp=t,
                source=f"RELAY_EVENT_REPORT:{source_name}",
                confidence="MEDIUM",
                evidence_ids=[f"report:{source_name}:{label}"],
                metadata={
                    "label": label,
                    "element": _element_from_label(label),
                    "file": source_name,
                },
            )
        )
    return out


def merge_timelines(
    primary: list[TimelineEvent],
    *extras: list[TimelineEvent],
) -> list[TimelineEvent]:
    """Merge and sort; drop near-duplicate same type within 2 ms from lower-priority sources."""
    merged = list(primary)
    for block in extras:
        merged.extend(block)
    merged.sort(key=lambda e: (e.timestamp, e.event_type))
    # Dedup: keep COMTRADE over SOE over report when nearly identical
    priority = {"COMTRADE": 0, "SOE": 1, "RELAY_EVENT_REPORT": 2}
    kept: list[TimelineEvent] = []
    for ev in merged:
        src_family = ev.source.split(":", 1)[0].upper()
        if src_family.startswith("SOE"):
            fam = "SOE"
        elif "REPORT" in src_family:
            fam = "RELAY_EVENT_REPORT"
        else:
            fam = "COMTRADE"
        dup = False
        for prev in kept:
            if prev.event_type != ev.event_type:
                continue
            if abs(prev.timestamp - ev.timestamp) > 0.002:
                continue
            prev_fam = (
                "SOE"
                if prev.source.upper().startswith("SOE")
                else (
                    "RELAY_EVENT_REPORT"
                    if "REPORT" in prev.source.upper()
                    else "COMTRADE"
                )
            )
            if priority.get(fam, 9) >= priority.get(prev_fam, 9):
                dup = True
                break
        if not dup:
            kept.append(ev)
    kept.sort(key=lambda e: (e.timestamp, e.event_type))
    return kept


def load_side_timeline_from_files(storage: Any, files: list[Any]) -> tuple[list[TimelineEvent], dict[str, Any]]:
    """Load SOE + event-report timeline events from uploaded EventFile rows."""
    events: list[TimelineEvent] = []
    summary: dict[str, Any] = {"soe": None, "event_report": None}

    for ef in files:
        name = (ef.original_filename or "").lower()
        try:
            raw = storage.get_bytes(ef.storage_key)
            text = raw.decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read side file %s: %s", name, exc)
            continue

        if name.endswith(".csv") and ("soe" in name or ef.source_type == "SOE"):
            parsed = parse_soe_csv(text, source_name=ef.original_filename or name)
            events.extend(parsed)
            summary["soe"] = {
                "file": ef.original_filename,
                "events": len(parsed),
            }
        elif (
            name.endswith(".txt")
            and (
                "event_report" in name
                or "relay_event" in name
                or ef.source_type == "RELAY_EVENT_REPORT"
            )
            and "setting" not in name
            and "readme" not in name
            and "upload_order" not in name
        ):
            parsed = parse_relay_event_report(text, source_name=ef.original_filename or name)
            events.extend(parsed)
            summary["event_report"] = {
                "file": ef.original_filename,
                "events": len(parsed),
            }

    return events, summary


def line_ct_vt_from_settings_data(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract line / CT-VT from settings JSON without requiring fixed field names.

    Uses flexible synonym detection (see ``param_detect.detect_plant_parameters``).
    Never invents values — only maps what is present under any reasonable key wording.
    """
    from app.services.param_detect import detect_plant_parameters

    det = detect_plant_parameters(data)
    return det.get("line") or {}, det.get("ct_vt") or {}
