"""Unit tests for high-value ANSI element registry additions."""

from __future__ import annotations

from protection.elements.base_dispatch import all_elements, get_element
from protection.engine import _match_element_from_channel


NEW_CODES = (
    "21G",
    "21P",
    "50P",
    "51P",
    "67P",
    "32R",
    "46",
    "68",
    "78",
    "87G",
    "87RGF",
)


def test_new_elements_registered():
    reg = all_elements()
    for code in NEW_CODES:
        assert code in reg, f"missing {code}"
        el = get_element(code)
        assert el is not None
        assert el.element_code == code


def test_channel_match_prefers_specific_suffix():
    assert _match_element_from_channel("TRIP_21G") == "21G"
    assert _match_element_from_channel("21P_PU") == "21P"
    assert _match_element_from_channel("50P") == "50P"
    assert _match_element_from_channel("51P_TRIP") == "51P"
    assert _match_element_from_channel("67P") == "67P"
    assert _match_element_from_channel("32R") == "32R"
    assert _match_element_from_channel("46_PU") == "46"
    assert _match_element_from_channel("68_BLK") == "68"
    assert _match_element_from_channel("78_OS") == "78"
    assert _match_element_from_channel("87G") == "87G"
    assert _match_element_from_channel("87RGF_OP") == "87RGF"
    # Generic still works
    assert _match_element_from_channel("50_TRIP") == "50"
    assert _match_element_from_channel("21_Z1") == "21"


def test_21g_assess_element_code():
    from protection.models import ElementContext, ElementObservation

    el = get_element("21G")
    assert el is not None
    ctx = ElementContext(
        observations=ElementObservation(element="21G"),
        settings={"enabled": True},
        setting_resolutions={},
        electrical={"fault_indicated": True},
        rule_config={},
    )
    res = el.assess(ctx)
    assert res.element == "21G"
