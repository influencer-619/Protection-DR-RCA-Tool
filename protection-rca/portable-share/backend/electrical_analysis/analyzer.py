"""Orchestrate signal processing over a CanonicalDisturbanceRecord."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from common.results import ALGORITHM_VERSION, SignalResult
from comtrade.canonical.model import CanonicalDisturbanceRecord
from signal_processing.derivatives import compute_di_dt, compute_dv_dt
from signal_processing.frequency import estimate_frequency
from signal_processing.harmonics import compute_harmonics
from signal_processing.impedance import compute_apparent_impedance
from signal_processing.phasor import compute_fundamental_phasor
from signal_processing.power import compute_power
from signal_processing.rms import compute_peak, compute_rms
from signal_processing.sequences import compute_sequence_components


@dataclass
class ElectricalAnalysisResult:
    """Aggregated electrical quantities for one disturbance record."""

    record_id: str
    nominal_frequency_hz: float
    sample_rate_hz: Optional[float]
    rms: dict[str, SignalResult] = field(default_factory=dict)
    peak: dict[str, SignalResult] = field(default_factory=dict)
    phasors: dict[str, SignalResult] = field(default_factory=dict)
    frequency: dict[str, SignalResult] = field(default_factory=dict)
    sequences: dict[str, SignalResult] = field(default_factory=dict)
    power: dict[str, SignalResult] = field(default_factory=dict)
    harmonics: dict[str, SignalResult] = field(default_factory=dict)
    derivatives: dict[str, SignalResult] = field(default_factory=dict)
    impedance: dict[str, SignalResult] = field(default_factory=dict)
    channel_roles: dict[str, str] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    algorithm_version: str = ALGORITHM_VERSION

    def to_dict(self) -> dict[str, Any]:
        def _sr(d: dict[str, SignalResult]) -> dict[str, Any]:
            return {k: v.to_dict() for k, v in d.items()}

        return {
            "record_id": self.record_id,
            "nominal_frequency_hz": self.nominal_frequency_hz,
            "sample_rate_hz": self.sample_rate_hz,
            "rms": _sr(self.rms),
            "peak": _sr(self.peak),
            "phasors": _sr(self.phasors),
            "frequency": _sr(self.frequency),
            "sequences": _sr(self.sequences),
            "power": _sr(self.power),
            "harmonics": _sr(self.harmonics),
            "derivatives": _sr(self.derivatives),
            "impedance": _sr(self.impedance),
            "channel_roles": self.channel_roles,
            "limitations": self.limitations,
            "algorithm_version": self.algorithm_version,
        }


def _infer_role(name: str, unit: str) -> str:
    # Normalize vendor punctuation: I_A, U-L1, IL1 → comparable tokens
    n = name.upper().replace(" ", "").replace("-", "").replace("_", "")
    u = (unit or "").upper()
    # Phase currents (ABB REF615 IL1/2/3, Siemens, GE, …)
    if n in ("IL1", "IL1A", "I1", "IA", "PHASEA", "CURRENTA", "CT1"):
        return "IA"
    if n in ("IL2", "IL2B", "I2", "IB", "PHASEB", "CURRENTB", "CT2"):
        return "IB"
    if n in ("IL3", "IL3C", "I3", "IC", "PHASEC", "CURRENTC", "CT3"):
        return "IC"
    if n in ("IO", "IG", "IR", "IN", "IRES", "IGND", "INOTAL", "IGROUND", "INEUTRAL"):
        return "IN"
    # Phase voltages (UL1 common in IEC naming)
    if n in ("UL1", "UL1A", "U1", "VA", "VL1", "PHASEVA", "VT1"):
        return "VA"
    if n in ("UL2", "UL2B", "U2", "VB", "VL2", "PHASEVB", "VT2"):
        return "VB"
    if n in ("UL3", "UL3C", "U3", "VC", "VL3", "PHASEVC", "VT3"):
        return "VC"
    if n in ("UN", "UG", "VN", "VG", "VNEUTRAL", "VGROUND"):
        return "VN"
    if any(x in n for x in ("IA", "IB", "IC", "IN", "CURRENT")) or u in ("A", "AMP", "AMPS"):
        if "IA" in n or n.endswith("A") and "V" not in n and n.startswith("I"):
            return "IA"
        if "IB" in n or (n.endswith("B") and n.startswith("I")):
            return "IB"
        if "IC" in n or (n.endswith("C") and n.startswith("I")):
            return "IC"
        if "IN" in n or "IG" in n or "IR" in n or "IO" in n:
            return "IN"
        return "I"
    if any(x in n for x in ("VA", "VB", "VC", "VN", "UL", "VOLT")) or u in ("V", "KV", "VOLT"):
        if "VA" in n or "UL1" in n:
            return "VA"
        if "VB" in n or "UL2" in n:
            return "VB"
        if "VC" in n or "UL3" in n:
            return "VC"
        if "VN" in n or "VG" in n or "UN" in n:
            return "VN"
        return "V"
    return "UNKNOWN"


def _better_role(ch_name: str, phase: str, unit: str) -> str:
    p = (phase or "").strip().upper()
    u = (unit or "").upper()
    n = ch_name.upper().replace(" ", "").replace("-", "").replace("_", "")
    is_current = u in ("A", "AMP", "AMPS") or (
        n.startswith("I") and not n.startswith("U") and "V" not in n[:1]
    )
    is_voltage = u in ("V", "KV", "VOLT") or n.startswith("U") or n.startswith("V")
    if is_current and not is_voltage:
        if p in ("A", "1"):
            return "IA"
        if p in ("B", "2"):
            return "IB"
        if p in ("C", "3"):
            return "IC"
        if p in ("N", "G", "0"):
            return "IN"
        return _infer_role(ch_name, unit)
    if is_voltage:
        if p in ("A", "1"):
            return "VA"
        if p in ("B", "2"):
            return "VB"
        if p in ("C", "3"):
            return "VC"
        if p in ("N", "G", "0"):
            return "VN"
        return _infer_role(ch_name, unit)
    return _infer_role(ch_name, unit)


def _primary_sample_rate(record: CanonicalDisturbanceRecord) -> Optional[float]:
    if record.sample_rates:
        for sec in record.sample_rates:
            rate = float(sec.sample_rate_hz or 0.0)
            if rate > 0:
                return rate
    if record.timestamps and len(record.timestamps) >= 2:
        dts = np.diff(np.asarray(record.timestamps, dtype=float))
        dts = dts[dts > 0]
        if len(dts):
            median_us = float(np.median(dts))
            if median_us > 0:
                return 1e6 / median_us
    return None


def _get_series(record: CanonicalDisturbanceRecord, name: str) -> list[float]:
    if name in record.scaled_values and record.scaled_values[name]:
        return list(record.scaled_values[name])
    if name in record.raw_values and record.raw_values[name]:
        return list(record.raw_values[name])
    return []


def _cycle_window_samples(sample_rate_hz: float, nominal_frequency_hz: float) -> int:
    return max(1, int(round(sample_rate_hz / max(nominal_frequency_hz, 1e-6))))


def _max_current_window_end(
    record: CanonicalDisturbanceRecord,
    role_to_name: dict[str, str],
    *,
    sample_rate_hz: float,
    nominal_frequency_hz: float,
) -> tuple[int, int]:
    """
    End index of the 1-cycle window with maximum phase-current energy.

    Disturbance files often continue after breaker open (currents ≈ 0). Using the
    final cycle then yields RMS=0 and fault type UNKNOWN — pick the faulted window.
    """
    window = _cycle_window_samples(sample_rate_hz, nominal_frequency_hz)
    names = [role_to_name.get(f"I{p}") for p in ("A", "B", "C")]
    series_list = []
    for n in names:
        if not n:
            continue
        s = np.asarray(_get_series(record, n), dtype=float)
        if s.size:
            series_list.append(s)
    if not series_list:
        # No phase currents — use longest analog series end
        longest = 0
        for ch in record.analog_channels:
            longest = max(longest, len(_get_series(record, ch.name)))
        end = max(0, longest - 1)
        return end, window

    n = int(min(s.size for s in series_list))
    if n <= 0:
        return 0, window
    if n < window:
        return n - 1, n

    energy = np.zeros(n, dtype=float)
    for s in series_list:
        energy += np.square(s[:n])
    csum = np.cumsum(energy)
    best_end = window - 1
    best_e = float(csum[best_end])
    for i in range(window, n):
        e = float(csum[i] - csum[i - window])
        if e > best_e:
            best_e = e
            best_end = i
    return best_end, window


def _window_slice(series: list[float], end_index: int, window: int) -> list[float]:
    if not series:
        return []
    end = min(max(0, end_index), len(series) - 1)
    start = max(0, end - window + 1)
    return series[start : end + 1]


def _timestamp_at(record: CanonicalDisturbanceRecord, index: int) -> Optional[float]:
    if not record.timestamps:
        return None
    if index < 0 or index >= len(record.timestamps):
        return float(record.timestamps[-1]) / 1e6
    return float(record.timestamps[index]) / 1e6


def analyze_electrical(
    record: CanonicalDisturbanceRecord,
    *,
    algorithm_version: str = ALGORITHM_VERSION,
) -> ElectricalAnalysisResult:
    """Run core signal-processing suite on a canonical COMTRADE record."""
    fs = _primary_sample_rate(record)
    f0 = record.nominal_frequency or 50.0
    result = ElectricalAnalysisResult(
        record_id=record.record_id,
        nominal_frequency_hz=f0,
        sample_rate_hz=fs,
        algorithm_version=algorithm_version,
    )

    if fs is None or fs <= 0:
        result.limitations.append(
            "Sample rate NOT AVAILABLE — many calculations NOT CALCULABLE"
        )
        return result

    role_to_name: dict[str, str] = {}
    for ch in record.analog_channels:
        role = _better_role(ch.name, ch.phase, ch.unit or record.units.get(ch.name, ""))
        result.channel_roles[ch.name] = role
        # Prefer specific IA/VA over generic I/V; first specific wins
        if role in ("UNKNOWN", "I", "V"):
            continue
        if role not in role_to_name:
            role_to_name[role] = ch.name

    fault_end, window = _max_current_window_end(
        record, role_to_name, sample_rate_hz=fs, nominal_frequency_hz=f0
    )
    ts_fault = _timestamp_at(record, fault_end)

    for ch in record.analog_channels:
        series = _get_series(record, ch.name)
        fault_series = _window_slice(series, fault_end, window)
        unit = ch.unit or record.units.get(ch.name, "")
        role = result.channel_roles.get(ch.name, "UNKNOWN")

        result.rms[ch.name] = compute_rms(
            fault_series,
            sample_rate_hz=fs,
            channel=ch.name,
            timestamp=ts_fault,
            unit=unit,
            nominal_frequency_hz=f0,
            algorithm_version=algorithm_version,
        )
        # Peak over full record (captures fault crest even if window RMS is used for typing)
        result.peak[ch.name] = compute_peak(
            series,
            channel=ch.name,
            timestamp=ts_fault,
            unit=unit,
            algorithm_version=algorithm_version,
        )
        result.phasors[ch.name] = compute_fundamental_phasor(
            fault_series,
            sample_rate_hz=fs,
            channel=ch.name,
            nominal_frequency_hz=f0,
            timestamp=ts_fault,
            unit=unit,
            algorithm_version=algorithm_version,
        )
        result.harmonics[ch.name] = compute_harmonics(
            fault_series,
            sample_rate_hz=fs,
            channel=ch.name,
            nominal_frequency_hz=f0,
            timestamp=ts_fault,
            unit=unit,
            algorithm_version=algorithm_version,
        )
        if role.startswith("I"):
            result.derivatives[ch.name] = compute_di_dt(
                fault_series,
                sample_rate_hz=fs,
                channel=ch.name,
                timestamp=ts_fault,
                algorithm_version=algorithm_version,
            )
            result.frequency[ch.name] = estimate_frequency(
                fault_series,
                sample_rate_hz=fs,
                channel=ch.name,
                timestamp=ts_fault,
                nominal_frequency_hz=f0,
                algorithm_version=algorithm_version,
            )
        elif role.startswith("V"):
            result.derivatives[ch.name] = compute_dv_dt(
                fault_series,
                sample_rate_hz=fs,
                channel=ch.name,
                timestamp=ts_fault,
                algorithm_version=algorithm_version,
            )
            result.frequency[ch.name] = estimate_frequency(
                fault_series,
                sample_rate_hz=fs,
                channel=ch.name,
                timestamp=ts_fault,
                nominal_frequency_hz=f0,
                algorithm_version=algorithm_version,
            )

    for prefix, key in (("I", "current_sequences"), ("V", "voltage_sequences")):
        names = [role_to_name.get(f"{prefix}{p}") for p in ("A", "B", "C")]
        if all(names):
            series_abc = [
                _window_slice(_get_series(record, n), fault_end, window)  # type: ignore[arg-type]
                for n in names
            ]
            result.sequences[key] = compute_sequence_components(
                *series_abc,
                sample_rate_hz=fs,
                channels=list(names),  # type: ignore[arg-type]
                nominal_frequency_hz=f0,
                timestamp=ts_fault,
                unit="A" if prefix == "I" else "V",
                algorithm_version=algorithm_version,
            )
        else:
            result.limitations.append(
                f"{key}: NOT AVAILABLE — missing three-phase {prefix} channels"
            )

    for phase in ("A", "B", "C"):
        vn = role_to_name.get(f"V{phase}")
        inan = role_to_name.get(f"I{phase}")
        if vn and inan:
            result.power[f"phase_{phase}"] = compute_power(
                _window_slice(_get_series(record, vn), fault_end, window),
                _window_slice(_get_series(record, inan), fault_end, window),
                sample_rate_hz=fs,
                voltage_channel=vn,
                current_channel=inan,
                nominal_frequency_hz=f0,
                timestamp=ts_fault,
                algorithm_version=algorithm_version,
            )
            result.impedance[f"phase_{phase}"] = compute_apparent_impedance(
                _window_slice(_get_series(record, vn), fault_end, window),
                _window_slice(_get_series(record, inan), fault_end, window),
                sample_rate_hz=fs,
                voltage_channel=vn,
                current_channel=inan,
                nominal_frequency_hz=f0,
                timestamp=ts_fault,
                algorithm_version=algorithm_version,
            )
        else:
            result.limitations.append(
                f"phase_{phase} power/impedance: NOT AVAILABLE — missing V{phase}/I{phase}"
            )

    return result
