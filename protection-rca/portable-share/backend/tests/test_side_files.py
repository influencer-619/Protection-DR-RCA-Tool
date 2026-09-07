"""Tests for SOE / relay event-report side-file parsing."""

from __future__ import annotations

from app.services.side_files import (
    merge_timelines,
    parse_relay_event_report,
    parse_soe_csv,
)
from event_reconstruction.timeline import TimelineEvent


SOE = """timestamp_utc,signal,value,source
2026-09-04T08:00:00.410000+00:00,21_Z1_PICKUP,1,TEST_DISTANCE_RELAY
2026-09-04T08:00:00.435000+00:00,21_Z1_TRIP,1,TEST_DISTANCE_RELAY
2026-09-04T08:00:00.465000+00:00,52A_CLOSED,0,TEST_BREAKER
"""

REPORT = """PROTECTION RELAY EVENT REPORT
Event ID: EVT-AG-132KV-FEEDER-001
Fault: A-G
Fault inception: 0.400 s
21 Z1 pickup: 0.410 s
21 Z1 trip: 0.435 s
51 pickup: 0.412 s
52A opens: 0.465 s
Synthetic test record only.
"""


def test_parse_soe_relative_times():
    evs = parse_soe_csv(SOE, source_name="soe.csv")
    assert len(evs) == 3
    assert abs(evs[0].timestamp - 0.410) < 1e-6
    assert evs[0].event_type == "protection_pickup"
    assert abs(evs[1].timestamp - 0.435) < 1e-6
    assert evs[1].event_type == "protection_trip"
    assert abs(evs[2].timestamp - 0.465) < 1e-6
    assert evs[2].event_type == "52a_change"
    assert evs[0].source.startswith("SOE:")


def test_parse_event_report():
    evs = parse_relay_event_report(REPORT, source_name="relay_event_report.txt")
    types = {e.event_type: e.timestamp for e in evs}
    assert abs(types["fault_inception"] - 0.400) < 1e-9
    assert abs(types["protection_pickup"] - 0.410) < 1e-9 or any(
        e.event_type == "protection_pickup" and abs(e.timestamp - 0.412) < 1e-9 for e in evs
    )
    assert any(e.event_type == "protection_trip" for e in evs)
    assert any(e.event_type == "52a_change" for e in evs)


def test_merge_prefers_comtrade_over_soe_duplicate():
    primary = [
        TimelineEvent(
            event_type="protection_pickup",
            timestamp=0.410,
            source="COMTRADE",
            confidence="HIGH",
        )
    ]
    soe = [
        TimelineEvent(
            event_type="protection_pickup",
            timestamp=0.4101,
            source="SOE:relay",
            confidence="HIGH",
        )
    ]
    merged = merge_timelines(primary, soe)
    assert len(merged) == 1
    assert merged[0].source == "COMTRADE"
