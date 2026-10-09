"""ANSI element physics — instantaneous OC, V/f thresholds, 87G/REF."""

from __future__ import annotations

from protection.elements.el_27 import Element_27
from protection.elements.el_50 import Element_50
from protection.elements.el_50n import Element_50N
from protection.elements.el_79 import Element_79
from protection.elements.el_81u import Element_81U
from protection.elements.el_87g import Element_87G
from protection.models import ElementContext, ElementObservation
from protection.physics import instantaneous_overcurrent, threshold_compare


def _ctx(
    code: str,
    *,
    settings: dict | None = None,
    electrical: dict | None = None,
    trip: bool | None = None,
    pickup: bool | None = None,
) -> ElementContext:
    return ElementContext(
        observations=ElementObservation(element=code, pickup=pickup, trip=trip),
        settings=settings or {"enabled": True},
        setting_resolutions={},
        electrical=electrical or {},
        timeline=[],
        rule_config={},
    )


def test_instantaneous_oc_helper():
    ok = instantaneous_overcurrent(current_a=1200.0, pickup_a=800.0)
    assert ok["status"] == "OK"
    assert ok["operate_expected"] is True
    no = instantaneous_overcurrent(current_a=100.0, pickup_a=800.0)
    assert no["operate_expected"] is False


def test_50_expects_operate_when_i_above_pickup():
    a = Element_50().assess(
        _ctx("50", settings={"enabled": True, "pickup_current": 500}, electrical={"I_max_a": 900})
    )
    assert a.expected_operation == "OPERATE"
    assert a.metadata["physics"]["status"] == "OK"


def test_50n_uses_residual():
    a = Element_50N().assess(
        _ctx("50N", settings={"enabled": True, "pickup_current": 50}, electrical={"I0": 80})
    )
    assert a.expected_operation == "OPERATE"
    assert a.metadata["physics"]["quantity"] == "I0"


def test_27_undervoltage():
    a = Element_27().assess(
        _ctx("27", settings={"enabled": True, "pickup_voltage": 80}, electrical={"V_min_v": 60})
    )
    assert a.expected_operation == "OPERATE"
    assert a.metadata["physics"]["mode"] == "under"


def test_81u_underfrequency():
    phys = threshold_compare(measured=49.2, pickup=49.5, mode="under", unit="Hz")
    assert phys["operate_expected"] is True
    a = Element_81U().assess(
        _ctx("81U", settings={"enabled": True, "pickup_hz": 49.5}, electrical={"frequency_hz": 49.0})
    )
    assert a.expected_operation == "OPERATE"


def test_79_not_driven_by_fault_indicated():
    a = Element_79().assess(
        _ctx("79", settings={"enabled": True}, electrical={"fault_indicated": True})
    )
    assert a.expected_operation != "OPERATE"
    assert a.metadata["physics"]["status"] == "SCHEME"


def test_79_shot_and_reclaim_success():
    from protection.models import ElementContext, ElementObservation

    ctx = ElementContext(
        observations=ElementObservation(element="79", pickup=True),
        settings={"enabled": True, "reclaim_s": 5.0, "max_shots": 3},
        setting_resolutions={},
        electrical={},
        timeline=[
            {"event_type": "protection_trip", "t_s": 0.10},
            {"event_type": "reclose", "t_s": 0.80},
            {"event_type": "current_interruption", "t_s": 0.85},
        ],
        rule_config={},
    )
    a = Element_79().assess(ctx)
    rc = a.metadata["physics"]["reclose"]
    assert rc["shots"] == 1
    assert rc["successful"] is True
    assert rc["reclaim_ok"] is True
    assert a.metadata.get("reclose_outcome") == "SUCCESSFUL"


def test_79_unsuccessful_retrip_and_lockout():
    from protection.models import ElementContext, ElementObservation

    ctx = ElementContext(
        observations=ElementObservation(element="79", pickup=True),
        settings={"enabled": True, "max_shots": 1},
        setting_resolutions={},
        electrical={},
        timeline=[
            {"event_type": "reclose", "t_s": 0.50},
            {"event_type": "protection_trip", "t_s": 0.70},
            {"event_type": "reclose", "t_s": 1.20},
        ],
        rule_config={},
    )
    a = Element_79().assess(ctx)
    rc = a.metadata["physics"]["reclose"]
    assert rc["shots"] == 2
    assert rc["lockout"] is True
    assert rc["unsuccessful"] is True


def test_87g_unverifiable_without_phasors_or_trip():
    a = Element_87G().assess(
        _ctx("87G", settings={"enabled": True}, electrical={"fault_indicated": True})
    )
    assert a.expected_operation == "UNKNOWN"
    assert a.consistency == "UNVERIFIABLE"


def test_49_thermal_i2t_overload():
    from protection.elements.el_49 import Element_49
    from protection.physics import thermal_i2t

    phys = thermal_i2t(current_a=150.0, flc_a=100.0, duration_s=120.0, tau_s=60.0)
    assert phys["status"] == "OK"
    assert phys["operate_expected"] is True
    a = Element_49().assess(
        _ctx(
            "49",
            settings={"enabled": True, "I_flc": 100.0, "thermal_tau_s": 60.0},
            electrical={"I_max_a": 160.0, "fault_duration_s": 90.0},
        )
    )
    assert a.expected_operation == "OPERATE"
    assert a.metadata["physics"]["status"] == "OK"


def test_25_sync_check_permit():
    from protection.elements.el_25 import Element_25
    from protection.physics import sync_check_25
    import cmath
    import math

    vb = cmath.rect(1.0, 0.0)
    vl = cmath.rect(0.99, math.radians(5.0))
    phys = sync_check_25(v_bus=vb, v_line=vl, f_bus_hz=50.0, f_line_hz=50.05)
    assert phys["permit_close"] is True
    a = Element_25().assess(
        _ctx(
            "25",
            settings={"enabled": True},
            electrical={
                "v_bus": {"magnitude": 1.0, "angle_deg": 0.0},
                "v_line": {"magnitude": 0.99, "angle_deg": 5.0},
                "frequency_hz": 50.0,
                "f_line_hz": 50.05,
            },
        )
    )
    assert a.expected_operation == "OPERATE"
    assert a.metadata["physics"]["status"] == "OK"


def test_25_dual_end_from_channel_phasors():
    """Bus/line voltages from COMTRADE channel names — not VA vs VB phases."""
    from protection.elements.el_25 import Element_25

    a = Element_25().assess(
        _ctx(
            "25",
            settings={"enabled": True},
            electrical={
                "phasors": {
                    "VBUS_A": {
                        "value": {"magnitude": 1.0, "angle_deg": 0.0},
                        "status": "OK",
                    },
                    "VLINE_A": {
                        "value": {"magnitude": 0.98, "angle_deg": 8.0},
                        "status": "OK",
                    },
                    # Phase voltages must not be used as sync sources
                    "VA": {"value": {"magnitude": 0.5, "angle_deg": 90.0}, "status": "OK"},
                    "VB": {"value": {"magnitude": 0.5, "angle_deg": -30.0}, "status": "OK"},
                },
                "frequency_hz": 50.0,
                "f_line_hz": 50.02,
            },
        )
    )
    assert a.metadata["physics"]["status"] == "OK"
    assert a.expected_operation == "OPERATE"
    assert a.metadata["physics"]["dphi_deg"] is not None
    assert abs(float(a.metadata["physics"]["dphi_deg"])) < 15


def test_25_does_not_use_phase_va_vb_as_sync_pair():
    from protection.elements.el_25 import Element_25

    a = Element_25().assess(
        _ctx(
            "25",
            settings={"enabled": True},
            electrical={
                "phasors": {
                    "VA": {"value": {"magnitude": 1.0, "angle_deg": 0.0}, "status": "OK"},
                    "VB": {"value": {"magnitude": 1.0, "angle_deg": -120.0}, "status": "OK"},
                },
            },
        )
    )
    assert a.metadata["physics"]["status"] == "NOT_CALCULABLE"


def test_21_multi_zone_z4_z5_reach():
    """Z1–Z5 reaches are evaluated; innermost in-zone wins for expected op."""
    from protection.elements.el_21 import Element_21

    a = Element_21().assess(
        _ctx(
            "21",
            settings={
                "enabled": True,
                "zone1_reach": 5.0,
                "zone2_reach": 10.0,
                "zone3_reach": 20.0,
                "zone4_reach": 40.0,
                "zone5_reach": 80.0,
                "zone_angle_deg": 75.0,
            },
            electrical={"R_ohm": 8.0, "X_ohm": 8.0},  # |Z|≈11.3 → outside Z1/Z2, in Z3+
            trip=True,
        )
    )
    mz = a.metadata["physics"]["multi_zone"]
    assert set(mz.keys()) == {"Z1", "Z2", "Z3", "Z4", "Z5"}
    assert mz["Z1"].get("in_zone") is False
    assert mz["Z2"].get("in_zone") is False
    assert mz["Z3"].get("in_zone") is True
    assert a.timing["innermost_in_zone"] == 3
    assert "Z4" in a.metadata["physics"]["zones_configured"]
    assert "Z5" in a.metadata["physics"]["zones_configured"]


def test_cascade_time_order_ok():
    from app.services.cascade_lbb import cascade_time_order

    order = cascade_time_order(
        [
            {"event_type": "protection_trip", "t_s": 0.10, "end_label": "INITIATOR"},
            {"event_type": "intertrip", "t_s": 0.25},
            {"event_type": "protection_trip", "t_s": 0.28, "end_label": "BACKUP"},
        ]
    )
    assert order["status"] == "OK"
    assert order["order_ok"] is True


def test_cascade_time_order_rejects_backup_first():
    from app.services.cascade_lbb import cascade_time_order

    order = cascade_time_order(
        [
            {"event_type": "protection_trip", "t_s": 0.30, "end_label": "BACKUP"},
            {"event_type": "protection_trip", "t_s": 0.40, "end_label": "INITIATOR"},
        ]
    )
    assert order["order_ok"] is False
