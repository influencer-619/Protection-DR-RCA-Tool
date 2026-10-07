from app.services.plant_service import kv_from_label


def test_kv_from_label_parses_common_names():
    assert kv_from_label("132kV") == 132.0
    assert kv_from_label("132 kV") == 132.0
    assert kv_from_label("33KV Bus") == 33.0
    assert kv_from_label("CAPF") is None
