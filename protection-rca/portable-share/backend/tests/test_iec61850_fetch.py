"""IEC 61850 acquisition against a simulated IED (libiec61850 server on localhost)."""

from __future__ import annotations

import json
import socket
import time
from pathlib import Path

import pytest

iec = pytest.importorskip("pyiec61850.pyiec61850")

from app.services.iec61850 import acquire as acq  # noqa: E402
from app.services.iec61850.settings_map import build_settings_document, element_for  # noqa: E402
from app.services.iec61850.vendors import detect_profile  # noqa: E402

CFG = """SIM-IED,REC001,1999
2,1A,1D
1,IA,A,,A,1.0,0.0,0,-32767,32767,800,1,P
1,TRIP,,,0
50
1
1000,2
12/07/2026,14:22:07.280000
12/07/2026,14:22:07.300000
ASCII
1
"""
DAT = "1,0,100,0\n2,1000,200,1\n"
EXTS = {".cfg", ".dat", ".hdr", ".inf", ".cff", ".txt", ".csv", ".json", ".log", ".xml", ".cid"}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _da(model, ref):
    node = iec.IedModel_getModelNodeByObjectReference(model, ref)
    assert node, ref
    return iec.toDataAttribute(node)


@pytest.fixture(scope="module")
def sim_ied(tmp_path_factory):
    root: Path = tmp_path_factory.mktemp("ied_fs")
    (root / "COMTRADE").mkdir()
    (root / "COMTRADE" / "REC001.cfg").write_bytes(CFG.encode())
    (root / "COMTRADE" / "REC001.dat").write_bytes(DAT.encode())
    (root / "COMTRADE" / "REC002.cfg").write_bytes(CFG.replace("REC001", "REC002").encode())
    (root / "SETTINGS").mkdir()
    (root / "SETTINGS" / "SET_1.TXT").write_text("[SET_1]\nCTR=800\n51P1P=1.2\n")
    (root / "EVENTS").mkdir()
    (root / "EVENTS" / "event_report.txt").write_text("Trip 51P A-phase\n")
    (root / "IED.cid").write_text("<SCL/>")

    model = iec.IedModel_create("SIM")
    ld = iec.LogicalDevice_create("PROT", model)
    iec.LogicalNode_create("LLN0", ld)
    lphd = iec.LogicalNode_create("LPHD1", ld)
    iec.CDC_DPL_create(
        "PhyNam",
        iec.toModelNode(lphd),
        iec.CDC_OPTION_DPL_MODEL | iec.CDC_OPTION_DPL_SWREV | iec.CDC_OPTION_DPL_SERNUM,
    )
    toc = iec.toModelNode(iec.LogicalNode_create("PHLPTOC1", ld))
    iec.CDC_ASG_create("StrVal", toc, 0, False)
    iec.CDC_ING_create("OpDlTmms", toc, 0)
    iec.CDC_ING_create("TmACrv", toc, 0)
    iec.CDC_ASG_create("TmMult", toc, 0, False)
    iec.CDC_ACD_create("Str", toc, 0)
    iec.CDC_ACT_create("Op", toc, 0)
    iec.CDC_ENS_create("Beh", toc, 0)
    dis = iec.toModelNode(iec.LogicalNode_create("PDIS1", ld))
    iec.CDC_ASG_create("PoRch", dis, 0, False)
    iec.CDC_ING_create("OpDlTmms", dis, 0)
    brf = iec.toModelNode(iec.LogicalNode_create("CCRBRF1", ld))
    iec.CDC_ING_create("FailTmms", brf, 0)
    ctr = iec.toModelNode(iec.LogicalNode_create("TCTR1", ld))
    iec.CDC_ASG_create("ARtg", ctr, 0, False)
    iec.CDC_ASG_create("ARtgSec", ctr, 0, False)

    srv = iec.IedServer_create(model)
    iec.IedServer_setFilestoreBasepath(srv, str(root) + "/")
    port = _free_port()
    iec.IedServer_start(srv, port)
    assert iec.IedServer_isRunning(srv)

    iec.IedServer_updateVisibleStringAttributeValue(srv, _da(model, "SIMPROT/LPHD1.PhyNam.vendor"), "ABB")
    iec.IedServer_updateVisibleStringAttributeValue(srv, _da(model, "SIMPROT/LPHD1.PhyNam.model"), "REF615")
    iec.IedServer_updateFloatAttributeValue(srv, _da(model, "SIMPROT/PHLPTOC1.StrVal.setMag.f"), 960.0)
    iec.IedServer_updateFloatAttributeValue(srv, _da(model, "SIMPROT/PHLPTOC1.TmMult.setMag.f"), 0.3)
    iec.IedServer_updateInt32AttributeValue(srv, _da(model, "SIMPROT/PHLPTOC1.TmACrv.setVal"), 9)
    iec.IedServer_updateInt32AttributeValue(srv, _da(model, "SIMPROT/PHLPTOC1.Beh.stVal"), 1)
    iec.IedServer_updateBooleanAttributeValue(srv, _da(model, "SIMPROT/PHLPTOC1.Op.general"), True)
    iec.IedServer_updateUTCTimeAttributeValue(srv, _da(model, "SIMPROT/PHLPTOC1.Op.t"), 1783866127322)
    iec.IedServer_updateFloatAttributeValue(srv, _da(model, "SIMPROT/PDIS1.PoRch.setMag.f"), 7.33)
    iec.IedServer_updateInt32AttributeValue(srv, _da(model, "SIMPROT/CCRBRF1.FailTmms.setVal"), 200)
    iec.IedServer_updateFloatAttributeValue(srv, _da(model, "SIMPROT/TCTR1.ARtg.setMag.f"), 800.0)
    iec.IedServer_updateFloatAttributeValue(srv, _da(model, "SIMPROT/TCTR1.ARtgSec.setMag.f"), 1.0)
    time.sleep(0.1)
    yield acq.Connection(host="127.0.0.1", port=port, connect_timeout_s=3, request_timeout_s=5)
    iec.IedServer_stop(srv)
    iec.IedServer_destroy(srv)


def test_identify_reads_nameplate_and_detects_vendor(sim_ied):
    info = acq.identify(sim_ied)
    assert info["logical_devices"] == ["SIMPROT"]
    assert info["nameplate"]["vendor"] == "ABB"
    assert info["nameplate"]["model"] == "REF615"
    assert info["detected_profile"] == "ABB"
    assert info["file_service"] is True


def test_browse_classifies_file_store(sim_ied):
    res = acq.browse(sim_ied)
    recs = {r["name"]: r for r in res["records"]}
    assert set(recs) == {"REC001", "REC002"}
    assert recs["REC001"]["complete"] is True
    assert recs["REC002"]["complete"] is False
    assert [f["name"] for f in res["settings_files"]] == ["SET_1.TXT"]
    assert [f["name"] for f in res["event_files"]] == ["event_report.txt"]
    assert [f["name"] for f in res["scl_files"]] == ["IED.cid"]


def test_acquire_downloads_record_settings_and_events(sim_ied):
    browse = acq.browse(sim_ied)
    key = next(r["key"] for r in browse["records"] if r["name"] == "REC001")
    res = acq.acquire(
        sim_ied,
        record_keys=[key],
        include_settings=True,
        include_events=True,
        include_scl=False,
        ied_label="F1-REL",
        allowed_exts=EXTS,
        max_bytes=10_000_000,
    )
    files = {p.filename: p for p in res.records[key]}
    assert files["REC001.cfg"].data.decode() == CFG
    assert files["REC001.dat"].data.decode() == DAT
    assert res.record_times[key].startswith("2026-07-12T14:22:07.3")

    shared = {p.filename: p for p in res.shared}
    assert "SET_1.TXT" in shared and "event_report.txt" in shared
    assert "IED.cid" not in shared

    doc = json.loads(shared["iec61850_settings_F1-REL.json"].data)
    assert doc["relay_model"] == "ABB REF615"
    p51 = doc["protection"]["51"]
    assert p51["pickup_current"] == pytest.approx(960.0)
    assert p51["time_dial"] == pytest.approx(0.3)
    assert p51["curve"] == "IEC Normal Inverse"
    assert p51["enabled"] is True
    assert doc["protection"]["21"]["zone1_reach"] == pytest.approx(7.33)
    assert doc["protection"]["50BF"]["bf_timer_s"] == pytest.approx(0.2)
    assert doc["ct_vt"]["ct_ratio"] == "800/1"
    assert doc["iec61850_raw"]["SIMPROT/PHLPTOC1.StrVal.setMag.f"] == pytest.approx(960.0)

    soe = shared["iec61850_soe_F1-REL.csv"].data.decode().splitlines()
    assert soe[0] == "Timestamp,Event_ID,IED,Point_Tag,Description,State"
    assert any("PHLPTOC1.Op" in row and row.endswith(",ON") for row in soe[1:])


def test_settings_document_is_ingestible():
    from app.services.file_service import infer_source_type
    from app.services.settings_ingest import ingest_settings_bytes

    doc = build_settings_document(
        ied_label="X",
        host="10.0.0.1",
        port=102,
        nameplate={"vendor": "Siemens", "model": "7SJ85"},
        ln_settings={"LD/I_PTOC1": {"StrVal.setMag.f": 1.5, "OpDlTmms.setVal": 40}},
        behaviour={},
        active_group=1,
        read_errors=[],
    )
    name = "iec61850_settings_X.json"
    assert infer_source_type(name) == "SETTINGS"
    ingested = ingest_settings_bytes(json.dumps(doc).encode(), filename=name)
    assert ingested["status"] == "OK"
    assert ingested["mapped"]["protection"]["50"]["pickup_current"] == 1.5


@pytest.mark.parametrize(
    ("ln", "dos", "expected"),
    [
        ("PHLPTOC1", {"StrVal", "TmACrv"}, "51"),
        ("PHHPTOC1", {"StrVal", "OpDlTmms"}, "50"),
        ("EFLPTOC1", {"StrVal", "TmMult"}, "51N"),
        ("DPHLPTOC1", {"StrVal", "DirMod"}, "67"),
        ("NSPTOC1", {"StrVal"}, "46"),
        ("PDIS2", {"PoRch"}, "21"),
        ("CCRBRF1", {"FailTmms"}, "50BF"),
        ("MMXU1", set(), None),
    ],
)
def test_element_mapping(ln, dos, expected):
    assert element_for(ln, dos) == expected


@pytest.mark.parametrize(
    ("vendor", "model", "expected"),
    [
        ("SEL", "SEL-421", "SEL"),
        ("Siemens", "7SA87", "SIEMENS"),
        ("GE Multilin", "D60", "GE"),
        ("Schneider Electric", "MiCOM P443", "SCHNEIDER"),
        ("Selectron", "X", "OTHER"),
    ],
)
def test_vendor_detection(vendor, model, expected):
    assert detect_profile({"vendor": vendor, "model": model}).id == expected
