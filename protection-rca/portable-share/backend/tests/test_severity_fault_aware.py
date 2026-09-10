"""Fault-aware consistency severity (NERC MIDAS-inspired)."""

from __future__ import annotations

from consistency.severity import adjust_finding_severity, event_severity_summary, fault_impact


def test_fault_impact_levels():
    assert fault_impact("AG", "CLASSIFIED") == 1
    assert fault_impact("ABC", "CLASSIFIED") == 3
    assert fault_impact("ABC", "UNKNOWN") == 0


def test_inconsistent_escalates_on_abc_unit_zone():
    sev = adjust_finding_severity(
        "MEDIUM",
        status="INCONSISTENT",
        element="87T",
        check_type="differential",
        fault_type="ABC",
        fault_status="CLASSIFIED",
    )
    assert sev in ("HIGH", "CRITICAL")


def test_unverifiable_capped():
    sev = adjust_finding_severity(
        "HIGH",
        status="UNVERIFIABLE",
        element="51",
        check_type="enabled_vs_pickup",
        fault_type="ABC",
        fault_status="CLASSIFIED",
    )
    assert sev == "MEDIUM"


def test_consistent_not_inflated():
    sev = adjust_finding_severity(
        "INFO",
        status="CONSISTENT",
        element="87T",
        check_type="enabled_vs_pickup",
        fault_type="ABC",
        fault_status="CLASSIFIED",
    )
    assert sev == "INFO"


def test_event_summary_uses_fault_floor():
    assert event_severity_summary(
        finding_severities=["INFO"],
        fault_type="ABC",
        fault_status="CLASSIFIED",
    ) == "HIGH"
    assert event_severity_summary(
        finding_severities=["INFO"],
        fault_type="AG",
        fault_status="CLASSIFIED",
    ) == "MEDIUM"
