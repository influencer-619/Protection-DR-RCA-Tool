"""Channel-map overlay on analyze_electrical."""

from __future__ import annotations

import math

from comtrade.canonical.model import AnalogChannel, CanonicalDisturbanceRecord, SampleRateSection
from electrical_analysis import analyze_electrical


def _sine(n=400, f=50.0, fs=4000.0, amp=10.0, phase=0.0):
    return [amp * math.sin(2 * math.pi * f * i / fs + phase) for i in range(n)]


def test_channel_map_overrides_roles():
    n = 400
    fs = 4000.0
    record = CanonicalDisturbanceRecord(
        record_id="map1",
        standard="IEEE",
        revision="1999",
        container="CFG_DAT",
        station="S",
        device="R",
        nominal_frequency=50.0,
        timestamps=[int(i * (1e6 / fs)) for i in range(n)],
        sample_rates=[SampleRateSection(sample_rate_hz=fs, end_sample=n)],
        analog_channels=[
            AnalogChannel(index=1, name="IL1", phase="A", unit="A"),
            AnalogChannel(index=2, name="WeirdV", phase="", unit="V"),
        ],
        digital_channels=[],
        samples=n,
        scaled_values={
            "IL1": _sine(n, amp=100),
            "WeirdV": _sine(n, amp=110, phase=0.1),
        },
        units={"IL1": "A", "WeirdV": "V"},
    )
    elec = analyze_electrical(record, channel_map={"WeirdV": "VA", "IL1": "IA"})
    assert elec.channel_roles["WeirdV"] == "VA"
    assert elec.channel_roles["IL1"] == "IA"
    assert "detectors" in elec.to_dict()
