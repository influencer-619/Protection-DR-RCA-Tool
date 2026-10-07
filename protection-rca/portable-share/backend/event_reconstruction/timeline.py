"""Event timeline reconstruction from COMTRADE analogs and digitals."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np

from app.core.enums import ConfidenceLevel
from comtrade.canonical.model import CanonicalDisturbanceRecord


@dataclass
class TimelineEvent:
    event_type: str
    timestamp: float  # seconds from record start
    source: str
    confidence: str
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_DIGITAL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Vendor-neutral digital roles (fallback when target map role is UNKNOWN)
    (re.compile(r"BF|50BF|BREAKER.?FAIL|\bLBB\b", re.I), "breaker_trip_command"),
    (re.compile(r"INTERTRIP|TRANSFER.?TRIP|(?<![A-Z0-9])TT\b", re.I), "intertrip"),
    # Trip before zone/start so "21_Z1_TRIP" is not classified as pickup
    (re.compile(
        r"TRIP|(?<![A-Z0-9])TR\b|_TR\b|OPERAT(?:E|ED)?|\bOPTD\b|_OP\b|(?<![A-Z0-9])OP\b",
        re.I,
    ), "protection_trip"),
    (re.compile(
        r"PICK(?:ED)?\s*UP|(?<![A-Za-z])PU(?![A-Za-z0-9])|"
        r"(?<![A-Za-z])START(?:ED)?(?![A-Za-z])|"
        r"ZONE\s*\d*\s*(?:PICK|START|PU)|Z[123](?:_|\s)*(?:PICK|START|PU)",
        re.I,
    ), "protection_pickup"),
    (re.compile(
        r"52A|52_A|CB.*52A|BKR\s*OFF|BREAKER\s*OFF|CB\s*OFF",
        re.I,
    ), "52a_change"),
    (re.compile(r"52B|52_B|BREAKER.*B\b|CB.*52B", re.I), "52b_change"),
    # Reclose — require clear AR wording; bare "AR"/"79" alone false-matches many DRs
    (re.compile(
        r"AUTO.?RECLOSE|RECLOSE|\bRREC\d*\b|INITIATE_?AR|"
        r"\b79\s*(?:AR|RECLOSE|RREC)\b|\bAR\s*(?:INIT|CLOSE|ON|OFF|SUCCESS)",
        re.I,
    ), "reclose"),
    (re.compile(r"LOCKOUT|\b86\b|LOCK.?OUT", re.I), "lockout"),
    (re.compile(
        r"(?<![A-Z])COMM(?![A-Z])|PILOT|CARRIER|POTT|DUTT",
        re.I,
    ), "communication_signal"),
]


def _sample_times(record: CanonicalDisturbanceRecord) -> np.ndarray:
    if record.timestamps:
        return np.asarray(record.timestamps, dtype=float) / 1e6
    n = record.samples
    if record.sample_rates and n:
        fs = record.sample_rates[0].sample_rate_hz
        if fs > 0:
            return np.arange(n, dtype=float) / fs
    return np.array([])


def _digital_transitions(
    series: list[float] | list[int], times: np.ndarray
) -> list[tuple[float, int, int]]:
    if not series or len(times) == 0:
        return []
    arr = np.asarray(series, dtype=int)
    n = min(len(arr), len(times))
    arr = arr[:n]
    t = times[:n]
    out = []
    for i in range(1, n):
        if arr[i] != arr[i - 1]:
            out.append((float(t[i]), int(arr[i - 1]), int(arr[i])))
    return out


def _rms_envelope(series: np.ndarray, fs: float, f0: float) -> np.ndarray:
    window = max(1, int(round(fs / f0)))
    if len(series) < window:
        return np.sqrt(np.maximum(series**2, 0))
    kernel = np.ones(window) / window
    mean_sq = np.convolve(series**2, kernel, mode="same")
    return np.sqrt(np.maximum(mean_sq, 0))


def _cfg_start_for_absolute(record: CanonicalDisturbanceRecord) -> Optional[datetime]:
    """COMTRADE CFG file start (first sample) — base for absolute sequence times."""
    start = getattr(record, "start_time", None)
    if start is None or not isinstance(start, datetime):
        return None
    # Treat missing / placeholder epochs as no absolute clock
    if start.year < 1990:
        return None
    if start.tzinfo is None:
        return start.replace(tzinfo=timezone.utc)
    return start


def stamp_absolute_times(
    events: list[TimelineEvent],
    record: CanonicalDisturbanceRecord,
) -> list[TimelineEvent]:
    """Set metadata.absolute_time = CFG start + relative seconds (IEEE C37.111).

    Leaves existing absolute_time (e.g. from SOE) unchanged.
    """
    start = _cfg_start_for_absolute(record)
    if start is None:
        return events
    for e in events:
        meta = e.metadata if isinstance(e.metadata, dict) else {}
        if meta.get("absolute_time"):
            continue
        try:
            abs_dt = start + timedelta(seconds=float(e.timestamp))
            meta = dict(meta)
            meta["absolute_time"] = abs_dt.isoformat()
            e.metadata = meta
        except (TypeError, ValueError, OverflowError):
            continue
    return events


def reconstruct_timeline(
    record: CanonicalDisturbanceRecord,
    *,
    current_increase_ratio: float = 2.0,
    voltage_drop_ratio: float = 0.85,
    digital_map: Optional[dict[str, Any]] = None,
) -> list[TimelineEvent]:
    """Detect timeline events. Returns empty list if insufficient data.

    ``digital_map`` (optional) remaps COMTRADE digital names to DR target roles
    (PICKUP/TRIP/52A/…) like an analog channel map.
    """
    from protection.digital_targets import (
        is_assert_transition,
        normalize_digital_map,
        resolve_digital_target,
        target_to_event_type,
    )

    events: list[TimelineEvent] = []
    times = _sample_times(record)
    if len(times) == 0:
        return events

    fs = float(record.sample_rates[0].sample_rate_hz) if record.sample_rates else 0.0
    f0 = record.nominal_frequency or 50.0
    cleaned_map = normalize_digital_map(digital_map)

    for dch in record.digital_channels:
        name = dch.name
        series = record.scaled_values.get(name) or record.raw_values.get(name) or []
        transitions = _digital_transitions(series, times)
        role, mapped_el = resolve_digital_target(name, digital_map=digital_map)
        matched_type = target_to_event_type(role)
        if name in cleaned_map:
            # Explicit map: IGNORE/UNKNOWN with no event → skip (no regex fallback)
            if matched_type is None:
                continue
        elif matched_type is None:
            for pat, etype in _DIGITAL_PATTERNS:
                if pat.search(name):
                    matched_type = etype
                    break
        if matched_type is None:
            continue
        normal = int(getattr(dch, "normal_state", 0) or 0)
        for t, frm, to in transitions:
            status_edge = matched_type in (
                "52a_change",
                "52b_change",
                "communication_signal",
            )
            if not status_edge and not is_assert_transition(frm, to, normal_state=normal):
                continue
            eid = f"ev-{uuid.uuid4().hex[:12]}"
            meta: dict[str, Any] = {
                "from": frm,
                "to": to,
                "channel": name,
                "target_role": role,
            }
            if mapped_el:
                meta["element"] = mapped_el
            events.append(
                TimelineEvent(
                    event_type=matched_type,
                    timestamp=t,
                    source=f"digital:{name}",
                    confidence=ConfidenceLevel.HIGH.value,
                    evidence_ids=[eid],
                    metadata=meta,
                )
            )

    if fs > 0:
        for ch in record.analog_channels:
            series_list = record.scaled_values.get(ch.name) or record.raw_values.get(
                ch.name
            )
            if not series_list:
                continue
            arr = np.asarray(series_list, dtype=float)
            n = min(len(arr), len(times))
            arr = arr[:n]
            t = times[:n]
            unit = (ch.unit or "").upper()
            name_u = ch.name.upper()
            env = _rms_envelope(arr, fs, f0)
            pre_n = min(len(env), max(1, int(2 * fs / f0)))
            baseline = float(np.median(env[:pre_n])) if pre_n else 0.0

            is_current = unit in ("A", "AMP", "AMPS") or (
                "I" in name_u and "V" not in name_u
            )
            is_voltage = unit in ("V", "KV") or "V" in name_u

            ch_unit = (ch.unit or ("A" if is_current else "V" if is_voltage else "")).strip()

            if is_current and baseline > 1e-6:
                thresh = baseline * current_increase_ratio
                idxs = np.where(env > thresh)[0]
                if len(idxs):
                    i0 = int(idxs[0])
                    rms_now = float(env[i0])
                    sample_now = float(arr[i0]) if i0 < len(arr) else rms_now
                    events.append(
                        TimelineEvent(
                            event_type="current_increase",
                            timestamp=float(t[i0]),
                            source=f"analog:{ch.name}",
                            confidence=ConfidenceLevel.MEDIUM.value,
                            evidence_ids=[f"ev-{uuid.uuid4().hex[:12]}"],
                            metadata={
                                "baseline_rms": baseline,
                                "threshold": thresh,
                                "value_rms": rms_now,
                                "value": sample_now,
                                "unit": ch_unit or "A",
                                "channel": ch.name,
                            },
                        )
                    )
                    events.append(
                        TimelineEvent(
                            event_type="fault_inception",
                            timestamp=float(t[i0]),
                            source=f"analog:{ch.name}",
                            confidence=ConfidenceLevel.MEDIUM.value,
                            evidence_ids=[f"ev-{uuid.uuid4().hex[:12]}"],
                            metadata={
                                "method": "current_rms_threshold",
                                "value_rms": rms_now,
                                "value": sample_now,
                                "unit": ch_unit or "A",
                                "channel": ch.name,
                            },
                        )
                    )
                peak = float(np.max(env))
                if peak > baseline * current_increase_ratio:
                    # Interrupt = sustained post-peak collapse, not the last samples
                    # of a truncated DR (EOF often looks like a drop → false interrupt).
                    peak_i = int(np.argmax(env))
                    after = env[peak_i:]
                    low_thresh = 0.1 * peak
                    low = np.where(after < low_thresh)[0]
                    if len(low):
                        ii = peak_i + int(low[0])
                        cycle = max(1, int(round(fs / f0)))
                        # Need ~½ cycle of sustained low *after* the drop index
                        sustain = max(1, cycle // 2)
                        # Ignore drops in the last ~2 cycles (DR end / buffer tail)
                        eof_guard = max(cycle, 2 * cycle)
                        room = len(env) - ii
                        if (
                            ii < len(t)
                            and room > eof_guard
                            and ii + sustain <= len(env)
                            and bool(np.all(env[ii : ii + sustain] < low_thresh))
                        ):
                            events.append(
                                TimelineEvent(
                                    event_type="current_interruption",
                                    timestamp=float(t[ii]),
                                    source=f"analog:{ch.name}",
                                    confidence=ConfidenceLevel.MEDIUM.value,
                                    evidence_ids=[f"ev-{uuid.uuid4().hex[:12]}"],
                                    metadata={
                                        "peak_rms": peak,
                                        "value_rms": float(env[ii]),
                                        "value": float(arr[ii])
                                        if ii < len(arr)
                                        else float(env[ii]),
                                        "unit": ch_unit or "A",
                                        "channel": ch.name,
                                    },
                                )
                            )

            if is_voltage and baseline > 1e-6:
                thresh = baseline * voltage_drop_ratio
                idxs = np.where(env < thresh)[0]
                if len(idxs):
                    i0 = int(idxs[0])
                    rms_now = float(env[i0])
                    sample_now = float(arr[i0]) if i0 < len(arr) else rms_now
                    events.append(
                        TimelineEvent(
                            event_type="voltage_change",
                            timestamp=float(t[i0]),
                            source=f"analog:{ch.name}",
                            confidence=ConfidenceLevel.MEDIUM.value,
                            evidence_ids=[f"ev-{uuid.uuid4().hex[:12]}"],
                            metadata={
                                "baseline_rms": baseline,
                                "threshold": thresh,
                                "value_rms": rms_now,
                                "value": sample_now,
                                "unit": ch_unit or "V",
                                "channel": ch.name,
                            },
                        )
                    )

    events.sort(key=lambda e: (e.timestamp, e.event_type))
    deduped: list[TimelineEvent] = []
    seen_fi = False
    seen_interrupt = False
    for e in events:
        if e.event_type == "fault_inception":
            if seen_fi:
                continue
            seen_fi = True
        if e.event_type == "current_interruption":
            if seen_interrupt:
                continue
            seen_interrupt = True
        deduped.append(e)
    # Absolute wall-clock from CFG start + relative sample time (standard practice)
    return stamp_absolute_times(deduped, record)
