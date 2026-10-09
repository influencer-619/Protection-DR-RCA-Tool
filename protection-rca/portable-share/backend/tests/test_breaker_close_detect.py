"""True breaker-close detection for SOTF — trip opens must not count as close."""

from __future__ import annotations

from event_reconstruction import TimelineEvent
from app.services.analysis_pipeline import (
    _current_persists_from_timeline,
    _timeline_indicates_breaker_close,
)


def test_current_persists_when_trip_without_interruption():
    events = [
        TimelineEvent(
            event_type="fault_inception",
            timestamp=0.05,
            source="analog",
            confidence="HIGH",
        ),
        TimelineEvent(
            event_type="current_increase",
            timestamp=0.05,
            source="analog",
            confidence="HIGH",
        ),
        TimelineEvent(
            event_type="protection_trip",
            timestamp=0.10,
            source="digital:TRIP",
            confidence="HIGH",
        ),
    ]
    assert _current_persists_from_timeline(events) is True


def test_current_does_not_persist_when_interrupted():
    events = [
        TimelineEvent(
            event_type="fault_inception",
            timestamp=0.05,
            source="analog",
            confidence="HIGH",
        ),
        TimelineEvent(
            event_type="protection_trip",
            timestamp=0.10,
            source="digital:TRIP",
            confidence="HIGH",
        ),
        TimelineEvent(
            event_type="current_interruption",
            timestamp=0.14,
            source="analog",
            confidence="HIGH",
        ),
    ]
    assert _current_persists_from_timeline(events) is False


def test_52a_open_is_not_close():
    ev = TimelineEvent(
        event_type="52a_change",
        timestamp=0.1,
        source="digital:52a",
        confidence="HIGH",
        metadata={"from": 1, "to": 0, "channel": "52a"},
    )
    assert _timeline_indicates_breaker_close([ev]) is False


def test_52a_rising_edge_is_close():
    ev = TimelineEvent(
        event_type="52a_change",
        timestamp=0.1,
        source="digital:52a",
        confidence="HIGH",
        metadata={"from": 0, "to": 1, "channel": "52a"},
    )
    assert _timeline_indicates_breaker_close([ev]) is True


def test_52b_falling_edge_is_close():
    ev = TimelineEvent(
        event_type="52b_change",
        timestamp=0.1,
        source="digital:52b",
        confidence="HIGH",
        metadata={"from": 1, "to": 0, "channel": "52b"},
    )
    assert _timeline_indicates_breaker_close([ev]) is True


def test_bare_52a_change_without_edges_is_not_close():
    ev = TimelineEvent(
        event_type="52a_change",
        timestamp=0.1,
        source="digital:52a",
        confidence="HIGH",
        metadata={"channel": "52a"},
    )
    assert _timeline_indicates_breaker_close([ev]) is False


def test_reclose_event_alone_is_not_sotf_close():
    """79 AR reclaim must not set breaker_close for Switch-onto-fault."""
    events = [
        TimelineEvent(
            event_type="protection_trip",
            timestamp=0.10,
            source="digital:TRIP",
            confidence="HIGH",
        ),
        TimelineEvent(
            event_type="reclose",
            timestamp=0.80,
            source="digital:79",
            confidence="HIGH",
        ),
    ]
    assert _timeline_indicates_breaker_close(events) is False


def test_52a_rising_after_trip_is_ar_not_sotf_close():
    events = [
        TimelineEvent(
            event_type="protection_trip",
            timestamp=0.10,
            source="digital:TRIP",
            confidence="HIGH",
        ),
        TimelineEvent(
            event_type="52a_change",
            timestamp=0.85,
            source="digital:52a",
            confidence="HIGH",
            metadata={"from": 0, "to": 1, "channel": "52a"},
        ),
    ]
    assert _timeline_indicates_breaker_close(events) is False


def test_52a_rising_before_trip_is_sotf_close():
    events = [
        TimelineEvent(
            event_type="52a_change",
            timestamp=0.05,
            source="digital:52a",
            confidence="HIGH",
            metadata={"from": 0, "to": 1, "channel": "52a"},
        ),
        TimelineEvent(
            event_type="fault_inception",
            timestamp=0.06,
            source="analog",
            confidence="HIGH",
        ),
        TimelineEvent(
            event_type="protection_trip",
            timestamp=0.12,
            source="digital:TRIP",
            confidence="HIGH",
        ),
    ]
    assert _timeline_indicates_breaker_close(events) is True
