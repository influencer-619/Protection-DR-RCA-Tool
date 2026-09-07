"""Event timeline reconstruction from COMTRADE analogs and digitals."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

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
    # ZONE* treated as pickup (distance zone assert); *_OP / bare OP as operate/trip
    (re.compile(r"PICK\s*UP|PU_|_PU\b|START|ZONE\s*\d*|Z[123]\b", re.I), "protection_pickup"),
    (re.compile(r"TRIP|TR\b|_TR\b|OPERATE|_OP\b|(?<![A-Z0-9])OP\b", re.I), "protection_trip"),
    (re.compile(r"52A|52_A|BREAKER.*A\b|CB.*52A", re.I), "52a_change"),
    (re.compile(r"52B|52_B|BREAKER.*B\b|CB.*52B", re.I), "52b_change"),
    (re.compile(r"RECLOSE|79\b|AR\b|AUTO.?RECLOSE", re.I), "reclose"),
    (re.compile(r"LOCKOUT|86\b|LO\b", re.I), "lockout"),
    (re.compile(r"INTERTRIP|TRANSFER.?TRIP|TT\b", re.I), "intertrip"),
    (re.compile(r"COMM|PILOT|CARRIER|POTT|DUTT", re.I), "communication_signal"),
    (re.compile(r"BF|50BF|BREAKER.?FAIL", re.I), "breaker_trip_command"),
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


def reconstruct_timeline(
    record: CanonicalDisturbanceRecord,
    *,
    current_increase_ratio: float = 2.0,
    voltage_drop_ratio: float = 0.85,
) -> list[TimelineEvent]:
    """Detect timeline events. Returns empty list if insufficient data."""
    events: list[TimelineEvent] = []
    times = _sample_times(record)
    if len(times) == 0:
        return events

    fs = float(record.sample_rates[0].sample_rate_hz) if record.sample_rates else 0.0
    f0 = record.nominal_frequency or 50.0

    for dch in record.digital_channels:
        name = dch.name
        series = record.scaled_values.get(name) or record.raw_values.get(name) or []
        transitions = _digital_transitions(series, times)
        matched_type = None
        for pat, etype in _DIGITAL_PATTERNS:
            if pat.search(name):
                matched_type = etype
                break
        if matched_type is None:
            continue
        for t, frm, to in transitions:
            eid = f"ev-{uuid.uuid4().hex[:12]}"
            events.append(
                TimelineEvent(
                    event_type=matched_type,
                    timestamp=t,
                    source=f"digital:{name}",
                    confidence=ConfidenceLevel.HIGH.value,
                    evidence_ids=[eid],
                    metadata={"from": frm, "to": to, "channel": name},
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

            if is_current and baseline > 1e-6:
                thresh = baseline * current_increase_ratio
                idxs = np.where(env > thresh)[0]
                if len(idxs):
                    i0 = int(idxs[0])
                    events.append(
                        TimelineEvent(
                            event_type="current_increase",
                            timestamp=float(t[i0]),
                            source=f"analog:{ch.name}",
                            confidence=ConfidenceLevel.MEDIUM.value,
                            evidence_ids=[f"ev-{uuid.uuid4().hex[:12]}"],
                            metadata={"baseline_rms": baseline, "threshold": thresh},
                        )
                    )
                    events.append(
                        TimelineEvent(
                            event_type="fault_inception",
                            timestamp=float(t[i0]),
                            source=f"analog:{ch.name}",
                            confidence=ConfidenceLevel.MEDIUM.value,
                            evidence_ids=[f"ev-{uuid.uuid4().hex[:12]}"],
                            metadata={"method": "current_rms_threshold"},
                        )
                    )
                peak = float(np.max(env))
                if peak > baseline * current_increase_ratio:
                    after = env[int(np.argmax(env)) :]
                    low = np.where(after < 0.1 * peak)[0]
                    if len(low):
                        ii = int(np.argmax(env)) + int(low[0])
                        if ii < len(t):
                            events.append(
                                TimelineEvent(
                                    event_type="current_interruption",
                                    timestamp=float(t[ii]),
                                    source=f"analog:{ch.name}",
                                    confidence=ConfidenceLevel.MEDIUM.value,
                                    evidence_ids=[f"ev-{uuid.uuid4().hex[:12]}"],
                                    metadata={"peak_rms": peak},
                                )
                            )

            if is_voltage and baseline > 1e-6:
                thresh = baseline * voltage_drop_ratio
                idxs = np.where(env < thresh)[0]
                if len(idxs):
                    i0 = int(idxs[0])
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
                            },
                        )
                    )

    events.sort(key=lambda e: (e.timestamp, e.event_type))
    deduped: list[TimelineEvent] = []
    seen_fi = False
    for e in events:
        if e.event_type == "fault_inception":
            if seen_fi:
                continue
            seen_fi = True
        deduped.append(e)
    return deduped
