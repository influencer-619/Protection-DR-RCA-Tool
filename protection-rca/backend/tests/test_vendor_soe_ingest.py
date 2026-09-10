"""Tests ensuring vendor settings, SOE/SER, and CFG/DAT-related side paths process correctly."""

from __future__ import annotations

from app.services.file_service import infer_source_type
from app.services.settings_ingest import (
    detect_vendor,
    ingest_settings_bytes,
    setting_records_from_ingested,
)
from app.services.side_files import (
    looks_like_soe_csv,
    parse_relay_event_report,
    parse_soe_csv,
)


SEL_SET_ALL = """[FID]
FID=SEL-421-5-R123-V0-Z003003-D20010101
[SET_1]
E51S=Y
51SP=1.20
51SC=U3
51STD=3.00
EZ1=Y
Z1MAG=8.50
CTR=1200
PTR=1000
LL=45.0
"""

SER_CSV = """Date,Time,Description,State,Device
01/15/2024,14:32:01.410,21_Z1_PICKUP,1,SEL-421
01/15/2024,14:32:01.435,21_Z1_TRIP,1,SEL-421
01/15/2024,14:32:01.465,52A_CLOSED,0,CB1
"""

PCM600_CSV = """Parameter,Value
pickup_a,5.0
time_dial,0.15
curve,IEC_NI
enabled,true
ct_ratio,600
vt_ratio,1100
length_km,12.5
"""

XRIO_XML = """<?xml version="1.0"?>
<Xrio>
  <Parameter name="pickup_a" value="2.5"/>
  <Parameter name="time_dial" value="0.2"/>
  <Setting>
    <Name>mta_deg</Name>
    <Value>-45</Value>
  </Setting>
</Xrio>
"""


def test_infer_source_types_for_vendor_files():
    assert infer_source_type("fault.cfg") == "COMTRADE"
    assert infer_source_type("fault.dat") == "COMTRADE"
    assert infer_source_type("record.cff") == "COMTRADE"
    assert infer_source_type("station_ser.csv") == "SOE"
    assert infer_source_type("SET_ALL.TXT") == "SETTINGS"
    assert infer_source_type("relay_settings.json") == "SETTINGS"
    assert infer_source_type("export.xrio") == "SETTINGS"
    assert infer_source_type("project.rdb") == "SETTINGS"
    assert infer_source_type("relay_event_report.txt") == "RELAY_EVENT_REPORT"
    assert infer_source_type("history_eve.txt") == "RELAY_EVENT_REPORT"


def test_detect_vendor_no_ge_false_positive():
    assert detect_vendor("large_feeder_settings.txt", "pickup=1") == "GENERIC"
    assert detect_vendor("SEL_SET_ALL.TXT", "FID=SEL-421") == "SEL"
    assert detect_vendor("abb_ref615_settings.txt", "RELION") == "ABB"
    assert detect_vendor("schneider_sepam.txt", "SEPAM") == "SCHNEIDER"


def test_sel_set_all_ingest_to_records():
    ingested = ingest_settings_bytes(SEL_SET_ALL.encode(), filename="SET_ALL.TXT")
    assert ingested["status"] == "OK"
    assert ingested["vendor"] == "SEL"
    flat, records = setting_records_from_ingested(ingested)
    els = {r.element for r in records}
    assert "51" in els or "21" in els
    assert any(
        r.parameter in ("pickup_current", "time_dial", "zone1_reach", "enabled")
        for r in records
    )
    assert flat.get("ct_ratio") == 1200 or "ct_ratio" in flat


def test_pcm600_csv_and_xrio():
    csv_ing = ingest_settings_bytes(PCM600_CSV.encode(), filename="pcm600_export.csv")
    assert csv_ing["status"] == "OK"
    assert (
        csv_ing["mapped"]["ct_vt"].get("ct_ratio") == 600
        or csv_ing["common"].get("ct_ratio") == 600
    )

    xml_ing = ingest_settings_bytes(XRIO_XML.encode(), filename="test.xrio")
    assert xml_ing["status"] == "OK"
    assert xml_ing["param_count"] >= 2


def test_rdb_not_invented():
    r = ingest_settings_bytes(b"\xd0\xcf\x11\xe0", filename="project.rdb")
    assert r["status"] == "NOT_CALCULABLE"
    assert "rdb" in (r.get("reason") or "").lower() or "ole" in (r.get("reason") or "").lower()


def test_ser_csv_date_time_columns():
    assert looks_like_soe_csv(SER_CSV)
    evs = parse_soe_csv(SER_CSV, source_name="station_ser.csv")
    assert len(evs) >= 2
    assert any(e.event_type == "protection_pickup" for e in evs)
    assert any(e.event_type == "protection_trip" for e in evs)


def test_event_report_cycles_unit():
    text = "21 Z1 Pickup at 20.5 cycles\nTRIP at 0.435 s\n"
    evs = parse_relay_event_report(text, source_name="sel_history.txt")
    assert any(e.event_type == "protection_pickup" for e in evs)
    assert any(e.event_type == "protection_trip" for e in evs)
