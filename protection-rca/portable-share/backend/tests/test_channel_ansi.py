"""Vendor-neutral fault / digital channel names → ANSI device numbers."""

from __future__ import annotations

import pytest

from protection.channel_ansi import match_ansi_from_channel
from protection.elements.base_dispatch import get_element
from protection.engine import _match_element_from_channel


@pytest.mark.parametrize(
    "name,ansi",
    [
        # --- Schneider / MiCOM ---
        ("I>1 Start", "50"),
        ("Start I>1", "50"),
        ("Trip I>1", "50"),
        ("I>2 Start", "51"),
        ("I>3 Trip", "51"),
        ("IN1>1 Start", "50N"),
        ("IN>1 Start", "50N"),
        ("IN>2 Start", "51N"),
        ("IEN>1", "50N"),
        ("I0>1 Start", "50N"),
        ("Trip ISEF>1", "50N"),
        ("Trip I2>1", "46"),
        ("Thermal Trip", "49"),
        ("Stall Rotor-run", "48"),
        ("Prolonged Start", "48"),
        # --- SEL Relay Word bits ---
        ("50P1", "50P"),
        ("50P2", "50P"),
        ("51P1T", "51P"),
        ("51G1", "51N"),
        ("51N1", "51N"),
        ("50N1", "50N"),
        ("50Q1", "46"),
        ("67P1", "67P"),
        ("67G1", "67N"),
        ("21P1", "21P"),
        ("21G1", "21G"),
        ("50BF", "50BF"),
        ("87T", "87T"),
        # --- Siemens SIPROTEC ---
        ("I> Pickup", "50"),
        ("IN> Trip", "50N"),
        ("I2> Start", "46"),
        ("I-DIFF Trip", "87T"),
        ("50/51 Pickup", "51"),
        ("5X-B Pickup", "51"),
        # --- IEC 61850 LN (ABB / Siemens / any) ---
        ("PIOC1", "50"),
        ("PHPIOC1.Op", "50"),
        ("PTOC1", "51"),
        ("PHLPTOC1", "51"),
        ("EFPIOC1", "50N"),
        ("EFLPTOC1", "51N"),
        ("NSPTOC1", "46"),
        ("PDIF1", "87T"),
        ("T2WPDIF1", "87T"),
        ("REFPDIF1", "87RGF"),
        ("PDIS1", "21"),
        ("PTUV1", "27"),
        ("PTOV1", "59"),
        ("PTUF1", "81U"),
        ("PTOF1", "81O"),
        ("RBRF1", "50BF"),
        ("RREC1", "79"),
        ("RSYN1", "25"),
        ("PTTR1", "49"),
        ("RPSB1", "68"),
        ("PPAM1", "78"),
        # --- GE / Multilin style English ---
        ("Phase IOC Trip", "50"),
        ("Phase TOC Pickup", "51"),
        ("Ground IOC", "50N"),
        ("Neutral TOC", "51N"),
        ("Transformer Diff Trip", "87T"),
        # --- Bare ANSI / underscored ---
        ("50P", "50P"),
        ("51P_TRIP", "51P"),
        ("TRIP_21G", "21G"),
        ("87_TRIP", "87T"),
        ("67N", "67N"),
        ("Diff> TRIP", "87T"),
        ("Diff picked up", "87T"),
        ("DIFF TRIP", "87L"),
        ("B DIFF TRIP", "87L"),
        ("Zone 1 Trip", "21"),
        ("Z1 Start", "21"),
        ("V<1 Start", "27"),
        ("V>1 Trip", "59"),
        ("F< Start", "81U"),
        ("F> Trip", "81O"),
        ("CBF Trip", "50BF"),
        # --- Skip generic / opaque / bay-prefixed station trip ---
        ("Fault Trip to TC", None),
        ("Trip", None),
        ("Any Start", None),
        ("Trip CMD", None),
        ("PTRC1", None),
        ("Relay 1", None),
        # Bay id "50BT" must NOT invent ANSI 50 (station unit trip)
        ("50BT STn Unit Ti", None),
        ("50BT STn Unit Trip", None),
        # Siemens / station DFR names from Bina Mam set
        ("O/C Ph L1 PU", "50"),
        ("OvercurrentTRIP", "50"),
        ("IE>> DIR. TRIP", "67N"),
        ("DIR O/C TRIP", "67"),
        ("ThOverload TRIP", "49"),
        ("BrkFailure TRIP", "50BF"),
        ("Bfail1 Trip 3ph", "50BF"),
        ("U/V Trip", "27"),
        ("VERS RPH DST ST", "21"),
    ],
)
def test_channel_names_map_to_ansi(name: str, ansi: str | None):
    assert match_ansi_from_channel(name) == ansi
    assert _match_element_from_channel(name) == ansi


def test_motor_elements_registered():
    for code in ("48", "49"):
        el = get_element(code)
        assert el is not None
        assert el.element_code == code


@pytest.mark.parametrize(
    "name",
    [
        "AR",
        "A/R",
        "79",
        "Digital 79",
        "Binary_79",
        "CARRIER",
        "ALARM",
        "START",
        "Phase A",
    ],
)
def test_bare_ar_or_79_does_not_invent_reclose(name: str):
    """Events list showed '79' with no AR channel in DR — stop bare AR/79 matches."""
    assert match_ansi_from_channel(name) != "79"
    assert _match_element_from_channel(name) != "79"


def test_clear_reclose_names_still_map_to_79():
    assert match_ansi_from_channel("RREC1") == "79"
    assert match_ansi_from_channel("Auto Reclose") == "79"
    assert match_ansi_from_channel("79 AR Success") == "79"
