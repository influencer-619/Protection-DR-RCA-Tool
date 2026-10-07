"""Siemens 7UT IDiff/IRest + BLK / trigger digital role inference."""

from electrical_analysis.analyzer import _infer_role
from protection.digital_targets import infer_target_role


def test_idiff_irest_and_ix1():
    assert _infer_role("IDiff-A", "A") == "IDIFF_A"
    assert _infer_role("IDiff-B", "A") == "IDIFF_B"
    assert _infer_role("IDiff-C", "A") == "IDIFF_C"
    assert _infer_role("IRest-A", "A") == "IREST_A"
    assert _infer_role("IRest-B", "A") == "IREST_B"
    assert _infer_role("IRest-C", "A") == "IREST_C"
    assert _infer_role("i-X1", "A") == "I"


def test_blk_and_recorder_digitals():
    assert infer_target_role("87 BLK 2nd H. A") == "BLOCK"
    assert infer_target_role("87 BLK nth H. B") == "BLOCK"
    assert infer_target_role("87 BLK CWA") == "BLOCK"
    assert infer_target_role(">Trig.Wave.Cap.") == "IGNORE"
    assert infer_target_role("FltRecSta") == "IGNORE"
    assert infer_target_role("Flag Lost") == "IGNORE"
    assert infer_target_role("87 TRIP") == "TRIP"
    assert infer_target_role("87 picked up") == "PICKUP"
