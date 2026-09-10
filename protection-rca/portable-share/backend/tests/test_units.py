"""Unit normalization and SI scaling for electrical quantities."""

from common.units import (
    infer_unit_from_quantity,
    normalize_unit,
    to_si_current_scale,
    to_si_voltage_scale,
)


def test_normalize_common_units():
    assert normalize_unit("a") == "A"
    assert normalize_unit("Amps") == "A"
    assert normalize_unit("kA") == "kA"
    assert normalize_unit("v") == "V"
    assert normalize_unit("KV") == "kV"
    assert normalize_unit("kilovolt") == "kV"
    assert normalize_unit("ohm") == "Ω"
    assert normalize_unit("ohms") == "Ω"
    assert normalize_unit("Ω") == "Ω"
    assert normalize_unit("Hz") == "Hz"
    assert normalize_unit("km") == "km"


def test_normalize_role_fallback():
    assert normalize_unit("", role="IA") == "A"
    assert normalize_unit(None, role="VA") == "V"
    assert normalize_unit("", role="Z_LOOP") == "Ω"


def test_si_scales_kv_ka():
    assert to_si_voltage_scale("kV") == 1000.0
    assert to_si_voltage_scale("V") == 1.0
    assert to_si_current_scale("kA") == 1000.0
    assert to_si_current_scale("A") == 1.0


def test_infer_from_quantity():
    assert infer_unit_from_quantity("Ia_rms", "amp") == "A"
    assert infer_unit_from_quantity("Va_rms", "kV") == "kV"
    assert infer_unit_from_quantity("Z_ab", "") == "Ω"
    assert infer_unit_from_quantity("freq", "") == "Hz"
