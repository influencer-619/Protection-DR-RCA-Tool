"""Load SOE CSV and relay event-report text into timeline contributions.

Never invents events — only parses what is present in uploaded side files.

Industry coverage (deterministic):
  - Generic / openXDA-style SOE CSV
  - SER / sequential-events CSV (SEL, station RTU exports)
  - Relay event reports (label: N s) and SEL-ish FID/DATE/TIME text
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
    (re.compile(r"PICK\s*UP|PICKUP|_PU\b|Z\d.*PU|START", re.I), "protection_pickup"),
    (re.compile(r"TRIP|_TR\b|OPERATE|Z\d.*TRIP|(?<![A-Z0-9])OP\b", re.I), "protection_trip"),
    (re.compile(r"52A|52_A|BREAKER.*OPEN|CB\s*OPEN|52A_CLOSED", re.I), "52a_change"),
    (re.compile(r"52B|52_B", re.I), "52b_change"),
    (re.compile(r"RECLOSE|79\b|AR\b", re.I), "reclose"),
    (re.compile(r"LOCKOUT|86\b", re.I), "lockout"),
    (re.compile(r"INTERTRIP|TRANSFER|TT\b", re.I), "intertrip"),
    (re.compile(r"50BF|BREAKER.?FAIL|BF\b", re.I), "breaker_trip_command"),
    (re.compile(r"COMM|CARRIER|PILOT|POTT|DUTT", re.I), "communication_signal"),
]

_REPORT_LINE = re.compile(
    r"^(?P<label>.+?):\s*(?P<t>[\d.]+)\s*(?:s|sec|seconds)?\s*$",
    re.I,
)

# SEL / vendor: "21 Z1 Pickup at 0.410 cycles" or "TRIP  12.5 cycles"
_REPORT_AT = re.compile(
    r"^(?P<label>.+?)\s+(?:at|=)\s*(?P<t>[\d.]+)\s*(?P<unit>s|sec|ms|cycles?)?\s*$",
    re.I,
)
_REPORT_TAB = re.compile(
    r"^(?P<label>[A-Za-z0-9_ /\-]+)\s{2,}(?P<t>[\d.]+)\s*(?P<unit>s|ms|cycles?)?\s*$",
    re.I,
)

_SOE_NAME_HINTS = (
    "soe",
    "ser",
    "sequential",
    "sequence_of_event",
    "eventlog",
    "event_log",
    "evtlog",
    "alarm_log",
    "status_log",
)

_REPORT_NAME_HINTS = (
    "event_report",
    "event-report",
    "relay_event",
    "ser_report",
    "history",
    "_eve",
    "eve.",
    "fault_report",
    "disturbance_report",
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
        pass
    # Common vendor: MM/DD/YYYY HH:MM:SS.mmm or DD-MM-YYYY ...
    for fmt in (
        "%m/%d/%Y %H:%M:%S.%f",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S.%f",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
        "%d-%b-%Y %H:%M:%S.%f",
        "%d-%b-%Y %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(text, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _element_from_label(label: str) -> Optional[str]:
    m = re.search(
        r"\b(87RGF|50BF|87G|87T|87L|87B|50N|51N|67N|67P|50P|51P|21G|21P|32R|81U|81O|81R|50|51|21|67|87|32|46|68|78|79|86|25|27|59)\b",
        label or "",
        re.I,
    )
    return m.group(1).upper() if m else None


def looks_like_soe_csv(text: str) -> bool:
    """Content sniff: CSV with time + signal/description columns."""
    sample = (text or "")[:4000]
    try:
        reader = csv.reader(io.StringIO(sample))
        header = next(reader, None)
    except Exception:  # noqa: BLE001
        return False
    if not header or len(header) < 2:
        return False
    joined = " ".join(h.strip().lower() for h in header)
    has_time = any(
        t in joined
        for t in ("time", "timestamp", "date", "datetime", "occurred")
    )
    has_sig = any(
        t in joined
        for t in (
            "signal",
            "event",
            "point",
            "description",
            "message",
            "channel",
            "status",
            "tag",
            "bit",
        )
    )
    return has_time and has_sig


def parse_soe_csv(
    text: str,
    *,
    source_name: str = "soe.csv",
    t0: Optional[datetime] = None,
) -> list[TimelineEvent]:
    """Parse SOE / SER CSV → TimelineEvent list."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return []
    fields = {(h or "").strip().lower(): h for h in reader.fieldnames}

    def _pick(*names: str) -> Optional[str]:
        for n in names:
            if n in fields:
                return fields[n]
        return None

    ts_key = _pick(
        "timestamp_utc",
        "timestamp",
        "datetime",
        "date_time",
        "event_time",
        "occurred",
    )
    date_key = _pick("date", "event_date")
    time_key = _pick("time", "time_only", "tod", "t")
    # Prefer Date+Time pair when both present (common SER export)
    if date_key and time_key:
        ts_key = None
    elif not ts_key:
        ts_key = _pick("time", "t")
    sig_key = _pick(
        "signal",
        "event",
        "point",
        "description",
        "message",
        "channel",
        "tag",
        "bit",
        "name",
        "status_text",
    )
    val_key = _pick("value", "state", "status", "new_state", "val")
    src_key = _pick("source", "device", "relay", "ied", "bay")
    if not sig_key:
        logger.warning("SOE CSV %s missing signal/description column", source_name)
        return []
    if not ts_key and not (date_key and time_key):
        logger.warning("SOE CSV %s missing timestamp columns", source_name)
        return []

    rows: list[tuple[datetime, str, str, Any]] = []
    for row in reader:
        if ts_key:
            dt = _parse_ts(str(row.get(ts_key) or ""))
        else:
            dt = _parse_ts(f"{row.get(date_key) or ''} {row.get(time_key) or ''}".strip())
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
        first = rows[0][0]
        t0 = first.replace(microsecond=0)

    out: list[TimelineEvent] = []
    for dt, sig, src, val in rows:
        # Skip de-assert / zero unless useful breaker status
        skip = False
        try:
            if val is not None and float(val) == 0 and "CLOSED" not in sig.upper():
                if "52A" not in sig.upper() and "52B" not in sig.upper():
                    skip = True
        except (TypeError, ValueError):
            if str(val).upper() in ("OFF", "FALSE", "DEASSERT", "RESET", "0"):
                if "52A" not in sig.upper() and "52B" not in sig.upper():
                    skip = True
        if skip:
            continue
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


def _to_seconds(t: float, unit: Optional[str]) -> float:
    u = (unit or "s").lower()
    if u.startswith("ms"):
        return t / 1000.0
    if u.startswith("cycle"):
        return t / 50.0  # assume 50 Hz; documented in metadata
    return t


def parse_relay_event_report(
    text: str,
    *,
    source_name: str = "relay_event_report.txt",
) -> list[TimelineEvent]:
    """Parse relay event report lines into timeline events."""
    out: list[TimelineEvent] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("=") or line.upper().startswith("PROTECTION"):
            continue
        if line.upper().startswith("FID=") or line.upper().startswith("DATE"):
            continue
        m = _REPORT_LINE.match(line) or _REPORT_AT.match(line) or _REPORT_TAB.match(line)
        if not m:
            continue
        label = m.group("label").strip()
        try:
            t_raw = float(m.group("t"))
        except (ValueError, IndexError):
            continue
        unit = None
        if "unit" in m.groupdict():
            unit = m.group("unit")
        t = _to_seconds(t_raw, unit)
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
                    "unit": unit or "s",
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


def _is_soe_file(name: str, source_type: Optional[str], text: str) -> bool:
    n = (name or "").lower()
    st = (source_type or "").upper()
    if st == "SOE":
        return n.endswith(".csv") or looks_like_soe_csv(text)
    if n.endswith(".csv") and any(h in n for h in _SOE_NAME_HINTS):
        return True
    if n.endswith(".csv") and looks_like_soe_csv(text) and "setting" not in n:
        return True
    return False


def _is_event_report_file(name: str, source_type: Optional[str]) -> bool:
    n = (name or "").lower()
    st = (source_type or "").upper()
    if any(x in n for x in ("setting", "readme", "upload_order", "set_all", "license")):
        return False
    if st == "RELAY_EVENT_REPORT":
        return n.endswith((".txt", ".log", ".eve", ".cev"))
    if n.endswith((".txt", ".log", ".eve")) and any(h in n for h in _REPORT_NAME_HINTS):
        return True
    # Generic .txt tagged as event report by extension default — try parse later
    if st == "RELAY_EVENT_REPORT" or (n.endswith(".txt") and "event" in n):
        return True
    return False


def load_side_timeline_from_files(storage: Any, files: list[Any]) -> tuple[list[TimelineEvent], dict[str, Any]]:
    """Load SOE + event-report timeline events from uploaded EventFile rows."""
    events: list[TimelineEvent] = []
    summary: dict[str, Any] = {"soe": None, "event_report": None, "files_tried": []}

    for ef in files:
        name = (ef.original_filename or "").lower()
        st = getattr(ef, "source_type", None)
        try:
            raw = storage.get_bytes(ef.storage_key)
            text = raw.decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read side file %s: %s", name, exc)
            continue

        if _is_soe_file(name, st, text):
            parsed = parse_soe_csv(text, source_name=ef.original_filename or name)
            events.extend(parsed)
            summary["soe"] = {
                "file": ef.original_filename,
                "events": len(parsed),
            }
            summary["files_tried"].append({"file": ef.original_filename, "kind": "SOE", "n": len(parsed)})
        elif _is_event_report_file(name, st):
            # Skip binary-ish CEV
            if name.endswith(".cev") and "\x00" in text[:200]:
                summary["files_tried"].append(
                    {
                        "file": ef.original_filename,
                        "kind": "RELAY_EVENT_REPORT",
                        "n": 0,
                        "note": "Binary CEV not parsed — use COMTRADE or ASCII event report",
                    }
                )
                continue
            parsed = parse_relay_event_report(text, source_name=ef.original_filename or name)
            if not parsed and (ef.original_filename or "").lower().endswith(".txt"):
                # Content may be settings mis-tagged — skip silently
                continue
            events.extend(parsed)
            summary["event_report"] = {
                "file": ef.original_filename,
                "events": len(parsed),
            }
            summary["files_tried"].append(
                {"file": ef.original_filename, "kind": "RELAY_EVENT_REPORT", "n": len(parsed)}
            )

    return events, summary


def line_ct_vt_from_settings_data(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Extract line / CT-VT from settings JSON without requiring fixed field names."""
    from app.services.param_detect import detect_plant_parameters

    det = detect_plant_parameters(data)
    return det.get("line") or {}, det.get("ct_vt") or {}
