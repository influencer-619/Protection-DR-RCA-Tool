"""DR digital targets — map override + rising-edge operate evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from comtrade.canonical.model import (
    CanonicalDisturbanceRecord,
    DigitalChannel,
    SampleRateSection,
)
from event_reconstruction import reconstruct_timeline
from protection.digital_targets import is_assert_transition, resolve_digital_target
from protection.engine import observations_from_timeline


def _record_with_digitals(
    series_by_name: dict[str, list[int]],
    *,
    normal: int = 0,
    start_time: datetime | None = None,
):
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
        start_time=start_time,
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


def test_actual_operation_pickup_vs_trip():
    from protection.models import _actual

    assert _actual(True, True) == "OPERATED"
    assert _actual(True, False) == "PICKED_UP"
    assert _actual(True, None) == "PICKED_UP"
    assert _actual(False, True) == "OPERATED"
    assert _actual(False, False) == "NOT_OPERATED"
    assert _actual(None, None) == "UNKNOWN"


def test_z1_trip_is_trip_not_pickup():
    from protection.digital_targets import infer_element_code, infer_target_role

    assert infer_target_role("21_Z1_TRIP") == "TRIP"
    assert infer_element_code("21_Z1_TRIP") == "21"
    assert infer_target_role("21_Z1_PICKUP") == "PICKUP"
    assert infer_element_code("21_Z1_PICKUP") == "21"


def test_intertrip_not_classified_as_trip():
    from protection.digital_targets import infer_target_role
    from protection.channel_ansi import match_ansi_from_channel

    assert infer_target_role("INTERTRIP_OUT") == "INTERTRIP"
    assert infer_target_role("INTERTRIP") == "INTERTRIP"
    assert infer_target_role("TRANSFER TRIP") == "INTERTRIP"
    assert infer_target_role("RECOMMENDATION") != "COMM"
    assert match_ansi_from_channel("PSB BLOCK") == "68"
    assert match_ansi_from_channel("INRUSH BLOCK") is None
    assert match_ansi_from_channel("68 BLOCK") == "68"


def test_shared_trip_cmd_attributes_all_pickups():
    from event_reconstruction.timeline import TimelineEvent

    tl = [
        TimelineEvent(
            event_type="protection_pickup",
            timestamp=0.10,
            source="digital:21_Z1_PICKUP",
            confidence="HIGH",
            metadata={"element": "21"},
        ),
        TimelineEvent(
            event_type="protection_pickup",
            timestamp=0.12,
            source="digital:51P_PICKUP",
            confidence="HIGH",
            metadata={"element": "51P"},
        ),
        TimelineEvent(
            event_type="protection_trip",
            timestamp=0.20,
            source="digital:TRIP_CMD",
            confidence="HIGH",
            metadata={"channel": "TRIP_CMD"},
        ),
    ]
    obs = observations_from_timeline(tl)
    assert obs["21"].trip is True
    assert obs["51P"].trip is True


def test_soe_orphan_trip_does_not_invent_50_when_21_pickup_exists():
    """Early SOE trip (different time base) must attribute to 21, not seed 50/51."""
    from event_reconstruction.timeline import TimelineEvent

    tl = [
        TimelineEvent(
            event_type="protection_trip",
            timestamp=0.026,
            source="SOE:IED",
            confidence="HIGH",
            metadata={"signal": "Distance Zone 1 operate", "element": None},
        ),
        TimelineEvent(
            event_type="protection_pickup",
            timestamp=0.301,
            source="digital:21_Z1_PICKUP",
            confidence="HIGH",
            metadata={"element": "21", "channel": "21_Z1_PICKUP"},
        ),
        TimelineEvent(
            event_type="protection_trip",
            timestamp=0.326,
            source="digital:TRIP_CMD",
            confidence="HIGH",
            metadata={"channel": "TRIP_CMD"},
        ),
    ]
    obs = observations_from_timeline(
        tl, electrical={"fault_indicated": True, "current_increase": True, "I0": 1.2}
    )
    assert "21" in obs and obs["21"].trip is True
    assert "50" not in obs
    assert "51" not in obs


def test_motor_protection_channel_inference():
    from protection.digital_targets import infer_element_code, infer_target_role

    assert infer_target_role("Thermal Alarm") == "ALARM"
    assert infer_element_code("Thermal Alarm") == "49"
    assert infer_target_role("Thermal Trip") == "TRIP"
    assert infer_element_code("Thermal Trip") == "49"
    assert infer_target_role("Stall Rotor-run") == "TRIP"
    assert infer_element_code("Stall Rotor-run") == "48"
    assert infer_target_role("Start I>1") == "PICKUP"
    assert infer_element_code("Start I>1") == "50"
    assert infer_target_role("I>1 Start") == "PICKUP"
    assert infer_element_code("I>1 Start") == "50"
    assert infer_target_role("IN1>1 Start") == "PICKUP"
    assert infer_element_code("IN1>1 Start") == "50N"
    assert infer_target_role("Trip I2>1") == "TRIP"
    assert infer_element_code("Trip I2>1") == "46"
    assert infer_target_role("Trip ISEF>1") == "TRIP"
    assert infer_element_code("Trip ISEF>1") == "50N"
    assert infer_target_role("Relay 1") == "IGNORE"
    assert infer_target_role("Relay 8") == "IGNORE"
    assert infer_target_role("CB Aux 3ph - 52A") == "52A"
    # CFG often truncates "Trip" → "Ti"
    assert infer_target_role("50BT STn Unit Ti") == "TRIP"
    assert infer_element_code("50BT STn Unit Ti") is None


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


def test_absolute_time_from_cfg_start_plus_relative():
    """IEEE practice: absolute = CFG start_time + relative sample time."""
    start = datetime(2026, 8, 19, 17, 5, 11, tzinfo=timezone.utc)
    # assert at sample index 5 → t = 5/4000 = 0.00125 s
    series = {"21_TRIP": [0] * 5 + [1] * 10}
    record = _record_with_digitals(series, start_time=start)
    events = reconstruct_timeline(record)
    trips = [e for e in events if e.event_type == "protection_trip"]
    assert len(trips) == 1
    abs_s = trips[0].metadata.get("absolute_time")
    assert abs_s
    abs_dt = datetime.fromisoformat(str(abs_s).replace("Z", "+00:00"))
    expected = start.timestamp() + trips[0].timestamp
    assert abs(abs_dt.timestamp() - expected) < 1e-6


def test_resolve_flat_map_syntax():
    role, el = resolve_digital_target("X", digital_map={"X": "PICKUP|51"})
    assert role == "PICKUP"
    assert el == "51"


def test_pickup_wording_is_vendor_neutral():
    """Common COMTRADE pickup phrasings — not tied to one manufacturer."""
    cases = [
        ("Relay PICKUP", "PICKUP", None),
        ("87 picked up", "PICKUP", "87T"),
        ("87G picked up", "PICKUP", "87G"),
        ("51P_START", "PICKUP", "51P"),
        ("STARTED_50N", "PICKUP", "50N"),
        ("PU_67N", "PICKUP", "67N"),
        ("O/C Earth PU", "PICKUP", None),
        ("Overcurrent PU", "PICKUP", None),
        ("VERS 67 X OPTD", "TRIP", "67"),
        ("VERS LBB OPTD", "BF", None),
        ("VERS RPH BKR OFF", "52A", None),
        ("GT-1 BREAKER OFF", "52A", None),
    ]
    for name, want_role, want_el in cases:
        role, el = resolve_digital_target(name)
        assert role == want_role, f"{name} -> {role}"
        if want_el:
            assert el == want_el, f"{name} el {el}"


def test_picked_up_channel_creates_timeline_pickup():
    series = {"Diff picked up": [0] * 8 + [1] * 12}
    record = _record_with_digitals(series)
    events = reconstruct_timeline(record)
    pickups = [e for e in events if e.event_type == "protection_pickup"]
    assert len(pickups) == 1
    assert pickups[0].source == "digital:Diff picked up"


def test_soe_bare_79_does_not_create_ar_pickup():
    """SOE '79' / reclose without COMTRADE digital must not invent AR pickup."""
    from event_reconstruction.timeline import TimelineEvent

    tl = [
        TimelineEvent(
            event_type="reclose",
            timestamp=0.5,
            source="SOE:relay",
            confidence="MEDIUM",
            metadata={"element": "79", "signal": "79"},
        ),
        TimelineEvent(
            event_type="protection_pickup",
            timestamp=0.4,
            source="SOE:relay",
            confidence="MEDIUM",
            metadata={"element": "79", "signal": "79"},
        ),
    ]
    obs = observations_from_timeline(tl)
    assert "79" not in obs


def test_station_soe_without_quality_does_not_assert():
    """Station SOE (no relay_ser quality) must not invent pickup/trip."""
    from event_reconstruction.timeline import TimelineEvent

    tl = [
        TimelineEvent(
            event_type="protection_pickup",
            timestamp=0.41,
            source="SOE:SCADA",
            confidence="MEDIUM",
            metadata={
                "element": "21",
                "signal": "SOME_ALARM",
                "evidence_quality": "station_soe",
            },
        ),
    ]
    obs = observations_from_timeline(tl)
    assert "21" not in obs


def test_relay_ser_clear_21_asserts_pickup():
    """Industry practice: clear relay SER / event report may assert with evidence."""
    from event_reconstruction.timeline import TimelineEvent

    tl = [
        TimelineEvent(
            event_type="protection_pickup",
            timestamp=0.41,
            source="SOE:IED",
            confidence="HIGH",
            metadata={
                "element": "21",
                "signal": "21_Z1_PICKUP",
                "point_tag": "21_Z1_PICKUP",
                "evidence_quality": "relay_ser",
            },
        ),
        TimelineEvent(
            event_type="protection_trip",
            timestamp=0.43,
            source="RELAY_EVENT_REPORT:eve.txt",
            confidence="MEDIUM",
            metadata={
                "element": "21",
                "label": "21 Z1 trip",
                "evidence_quality": "relay_ser",
            },
        ),
    ]
    obs = observations_from_timeline(tl)
    assert obs["21"].pickup is True
    assert obs["21"].trip is True
    assert any(str(e).startswith("ser:") for e in obs["21"].channel_evidence)
    assert any(str(e).startswith("report:") for e in obs["21"].channel_evidence)


def test_relay_ser_auto_reclose_asserts_79():
    from event_reconstruction.timeline import TimelineEvent

    tl = [
        TimelineEvent(
            event_type="reclose",
            timestamp=0.8,
            source="SOE:IED",
            confidence="HIGH",
            metadata={
                "element": "79",
                "signal": "Auto Reclose initiate",
                "evidence_quality": "relay_ser",
            },
        ),
    ]
    obs = observations_from_timeline(tl)
    assert obs["79"].pickup is True
    assert any("ser:" in str(e) for e in obs["79"].channel_evidence)


def test_inhibit_ar_digital_does_not_assert_79_pickup():
    """INHIBIT AR is supervisory — must not appear as 79 pickup on summary."""
    from event_reconstruction.timeline import TimelineEvent

    tl = [
        TimelineEvent(
            event_type="reclose",
            timestamp=0.2,
            source="digital:INHIBIT AR",
            confidence="HIGH",
            metadata={"element": "79", "channel": "INHIBIT AR", "target_role": "BLOCK"},
        ),
        TimelineEvent(
            event_type="protection_pickup",
            timestamp=0.3,
            source="digital:AR_INHIBITED",
            confidence="HIGH",
            metadata={"element": "79", "channel": "AR_INHIBITED"},
        ),
    ]
    obs = observations_from_timeline(tl)
    assert "79" not in obs or obs["79"].pickup is not True


def test_clear_ar_digital_still_creates_79_pickup():
    from event_reconstruction.timeline import TimelineEvent

    tl = [
        TimelineEvent(
            event_type="reclose",
            timestamp=0.5,
            source="digital:RREC1",
            confidence="HIGH",
            metadata={"element": "79"},
        ),
    ]
    obs = observations_from_timeline(tl)
    assert obs["79"].pickup is True
    assert "RREC1" in obs["79"].channel_evidence


def test_orphan_trip_cmd_attributed_to_pickup_element():
    """Shared TRIP_CMD (no ANSI in name) → trip on the element that picked up."""
    series = {
        "51P_PICKUP": [0] * 10 + [1] * 40,
        "50P_INST_TRIP": [0] * 50,
        "TRIP_CMD": [0] * 30 + [1] * 20,
        "CB_52A_STATUS": [1] * 40 + [0] * 10,
    }
    record = _record_with_digitals(series)
    events = reconstruct_timeline(record)
    assert any(
        e.event_type == "protection_trip" and e.source == "digital:TRIP_CMD" for e in events
    )
    obs = observations_from_timeline(events)
    assert obs["51P"].pickup is True
    assert obs["51P"].trip is True
    assert obs["51P"].trip_time_s is not None
    assert "TRIP_CMD" in obs["51P"].channel_evidence
    # Instantaneous trip channel present but never asserted
    assert obs.get("50P") is None or obs["50P"].trip is not True
