"""DR digital targets — map override + rising-edge operate evidence."""

from __future__ import annotations

from comtrade.canonical.model import (
    CanonicalDisturbanceRecord,
    DigitalChannel,
    SampleRateSection,
)
from event_reconstruction import reconstruct_timeline
from protection.digital_targets import is_assert_transition, resolve_digital_target
from protection.engine import observations_from_timeline


def _record_with_digitals(series_by_name: dict[str, list[int]], *, normal: int = 0):
    n = max(len(v) for v in series_by_name.values())
    fs = 4000.0
    return CanonicalDisturbanceRecord(
        record_id="dig1",
        standard="IEEE",
        revision="1999",
        container="CFG_DAT",
        station="S",
        device="R",
        nominal_frequency=50.0,
        timestamps=[int(i * (1e6 / fs)) for i in range(n)],
        sample_rates=[SampleRateSection(sample_rate_hz=fs, end_sample=n)],
        analog_channels=[],
        digital_channels=[
            DigitalChannel(index=i + 1, name=name, normal_state=normal)
            for i, name in enumerate(series_by_name)
        ],
        samples=n,
        scaled_values=series_by_name,
        units={},
    )


def test_is_assert_rising_and_falling():
    assert is_assert_transition(0, 1, normal_state=0)
    assert not is_assert_transition(1, 0, normal_state=0)
    assert is_assert_transition(1, 0, normal_state=1)
    assert not is_assert_transition(0, 1, normal_state=1)


def test_map_overrides_opaque_name_to_trip_21():
    # Opaque vendor name: without map → no operate; with map → TRIP on 21
    series = {"BIN_07": [0] * 10 + [1] * 20}
    record = _record_with_digitals(series)
    bare = reconstruct_timeline(record)
    assert not any(e.event_type == "protection_trip" for e in bare)

    mapped = reconstruct_timeline(
        record, digital_map={"BIN_07": {"role": "TRIP", "element": "21"}}
    )
    trips = [e for e in mapped if e.event_type == "protection_trip"]
    assert len(trips) == 1
    assert trips[0].metadata.get("element") == "21"
    assert trips[0].metadata.get("target_role") == "TRIP"

    obs = observations_from_timeline(
        mapped, digital_map={"BIN_07": {"role": "TRIP", "element": "21"}}
    )
    assert "21" in obs
    assert obs["21"].trip is True


def test_rising_edge_only_for_trip():
    # 0→1 then 1→0: only assert edge becomes protection_trip
    series = {"21_TRIP": [0] * 5 + [1] * 10 + [0] * 10}
    record = _record_with_digitals(series)
    events = reconstruct_timeline(record)
    trips = [e for e in events if e.event_type == "protection_trip"]
    assert len(trips) == 1
    assert trips[0].metadata["from"] == 0
    assert trips[0].metadata["to"] == 1


def test_ignore_role_skips_channel():
    series = {"TRIP_A": [0] * 5 + [1] * 10}
    record = _record_with_digitals(series)
    events = reconstruct_timeline(record, digital_map={"TRIP_A": {"role": "IGNORE"}})
    assert not any(e.source == "digital:TRIP_A" for e in events)


def test_resolve_flat_map_syntax():
    role, el = resolve_digital_target("X", digital_map={"X": "PICKUP|51"})
    assert role == "PICKUP"
    assert el == "51"
