"""Current interruption must not fire on DR end / truncated tail."""

from __future__ import annotations

import math

import numpy as np

from comtrade.canonical.model import (
    AnalogChannel,
    CanonicalDisturbanceRecord,
    SampleRateSection,
)
from event_reconstruction import reconstruct_timeline


def _current_record(ia: list[float], *, fs: float = 1000.0) -> CanonicalDisturbanceRecord:
    n = len(ia)
    return CanonicalDisturbanceRecord(
        record_id="eof-i",
        standard="IEEE",
        revision="1999",
        container="CFG_DAT",
        station="S",
        device="R",
        nominal_frequency=50.0,
        timestamps=[int(i * (1e6 / fs)) for i in range(n)],
        sample_rates=[SampleRateSection(sample_rate_hz=fs, end_sample=n)],
        analog_channels=[
            AnalogChannel(index=1, name="IA", phase="A", unit="A", primary=1.0, secondary=1.0)
        ],
        digital_channels=[],
        samples=n,
        scaled_values={"IA": ia},
        units={"IA": "A"},
    )


def _sine(n: int, amp: float, fs: float = 1000.0, f0: float = 50.0) -> list[float]:
    return [amp * math.sin(2 * math.pi * f0 * i / fs) for i in range(n)]


def test_no_interrupt_when_fault_runs_to_eof():
    """High fault current until last samples — EOF drop is not interruption."""
    fs = 1000.0
    pre = _sine(200, 0.4, fs=fs)
    fault = _sine(750, 8.0, fs=fs)  # stays high to end (~950 ms)
    ia = pre + fault
    events = reconstruct_timeline(_current_record(ia, fs=fs))
    interrupts = [e for e in events if e.event_type == "current_interruption"]
    assert interrupts == [], [e.timestamp for e in interrupts]


def test_interrupt_when_current_clears_mid_record():
    """Clear mid-record with sustained low — still detected."""
    fs = 1000.0
    pre = _sine(100, 0.4, fs=fs)
    fault = _sine(200, 8.0, fs=fs)
    cleared = _sine(500, 0.05, fs=fs)  # long post-clear buffer
    ia = pre + fault + cleared
    events = reconstruct_timeline(_current_record(ia, fs=fs))
    interrupts = [e for e in events if e.event_type == "current_interruption"]
    assert len(interrupts) >= 1
    assert interrupts[0].timestamp < 0.45  # not at DR end (~0.8 s)
