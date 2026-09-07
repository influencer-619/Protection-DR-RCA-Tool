#!/usr/bin/env python3
"""Generate synthetic COMTRADE fixtures for the golden regression matrix.

Creates IEEE 1991, BINARY, BINARY32, FLOAT32, and CFF variants from the
ASCII IEEE 1999 AG fault sample. Synthetic only — for parser regression.
"""

from __future__ import annotations

import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "test_data" / "comtrade"
SRC_CFG = ROOT / "ieee_1999" / "ag_fault.cfg"
SRC_DAT = ROOT / "ieee_1999" / "ag_fault.dat"


def _read_ascii_samples(dat_text: str, n_analog: int, n_digital: int) -> list[tuple]:
    rows = []
    for line in dat_text.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 2 + n_analog:
            continue
        n = int(parts[0])
        t = int(float(parts[1]))
        analogs = [int(float(x)) for x in parts[2 : 2 + n_analog]]
        digitals = []
        if n_digital and len(parts) > 2 + n_analog:
            digitals = [int(float(x)) for x in parts[2 + n_analog : 2 + n_analog + n_digital]]
        while len(digitals) < n_digital:
            digitals.append(0)
        rows.append((n, t, analogs, digitals))
    return rows


def write_1991() -> None:
    out = ROOT / "ieee_1991"
    out.mkdir(parents=True, exist_ok=True)
    # 1991: first line has no year field
    cfg = """TEST_STATION_1991,REL_01
6,4A,2D
1,Ia,A,Line1,A,0.1,0.0,0,-32767,32767,1000,1,P
2,Ib,B,Line1,A,0.1,0.0,0,-32767,32767,1000,1,P
3,Ic,C,Line1,A,0.1,0.0,0,-32767,32767,1000,1,P
4,Va,A,Bus1,V,0.05,0.0,0,-32767,32767,110000,110,P
1,TRIP,A,,0
2,52A,A,,1
50
1
1000.0,100
04/09/2026,11:58:00.000000
04/09/2026,11:58:00.050000
ASCII
1
"""
    (out / "ag_fault.cfg").write_text(cfg, encoding="utf-8")
    (out / "ag_fault.dat").write_bytes(SRC_DAT.read_bytes())


def _pack_binary(rows, n_analog: int, n_digital: int, fmt: str) -> bytes:
    """fmt: binary16 | binary32 | float32"""
    out = bytearray()
    digital_words = (n_digital + 15) // 16
    for n, t, analogs, digitals in rows:
        out += struct.pack("<I", n)
        out += struct.pack("<i", t)
        for a in analogs:
            if fmt == "binary16":
                out += struct.pack("<h", max(-32768, min(32767, int(a))))
            elif fmt == "binary32":
                out += struct.pack("<i", int(a))
            else:
                out += struct.pack("<f", float(a) * 0.1)  # scaled engineering-ish
        # pack digitals into 16-bit words
        for w in range(digital_words):
            word = 0
            for b in range(16):
                idx = w * 16 + b
                if idx < len(digitals) and digitals[idx]:
                    word |= 1 << b
            out += struct.pack("<H", word)
    return bytes(out)


def write_binary_variants() -> None:
    cfg_text = SRC_CFG.read_text(encoding="utf-8")
    dat_text = SRC_DAT.read_text(encoding="utf-8")
    rows = _read_ascii_samples(dat_text, 4, 2)

    variants = [
        ("binary16", "BINARY", "ieee_binary"),
        ("binary32", "BINARY32", "ieee_binary32"),
        ("float32", "FLOAT32", "ieee_float32"),
    ]
    for fmt, label, folder in variants:
        out = ROOT / folder
        out.mkdir(parents=True, exist_ok=True)
        lines = cfg_text.splitlines()
        # Replace ASCII with format label (last format line before CR/LF count)
        for i, line in enumerate(lines):
            if line.strip().upper() in ("ASCII", "BINARY", "BINARY32", "FLOAT32"):
                lines[i] = label
        (out / "ag_fault.cfg").write_text("\n".join(lines) + "\n", encoding="utf-8")
        (out / "ag_fault.dat").write_bytes(_pack_binary(rows, 4, 2, fmt))


def write_cff() -> None:
    """Minimal CFF: CFG + DAT ASCII sections concatenated with markers."""
    out = ROOT / "cff"
    out.mkdir(parents=True, exist_ok=True)
    cfg = SRC_CFG.read_text(encoding="utf-8")
    dat = SRC_DAT.read_text(encoding="utf-8")
    # Common single-file CFF style used by some recorders
    body = (
        "--- file type: CFG ---\n"
        + cfg
        + "--- file type: DAT ---\n"
        + dat
    )
    (out / "ag_fault.cff").write_text(body, encoding="utf-8")


def write_goldens() -> None:
    golden = Path(__file__).resolve().parents[1] / "test_data" / "golden"
    cases = {
        "EVT-SYNTH-1991-AG": {
            "comtrade_version": "IEEE C37.111-1991",
            "support_status": "PARTIALLY_SUPPORTED",
            "fixture": "comtrade/ieee_1991/ag_fault.cfg",
            "channel_count_analog": 4,
            "channel_count_digital": 2,
            "sample_rate_hz": 1000.0,
            "expected_fault": "AG",
        },
        "EVT-SYNTH-BIN16-AG": {
            "comtrade_version": "IEEE C37.111-1999",
            "data_format": "BINARY",
            "support_status": "SUPPORTED",
            "fixture": "comtrade/ieee_binary/ag_fault.cfg",
            "channel_count_analog": 4,
            "sample_rate_hz": 1000.0,
        },
        "EVT-SYNTH-BIN32-AG": {
            "comtrade_version": "IEEE C37.111-1999",
            "data_format": "BINARY32",
            "support_status": "SUPPORTED",
            "fixture": "comtrade/ieee_binary32/ag_fault.cfg",
        },
        "EVT-SYNTH-F32-AG": {
            "comtrade_version": "IEEE C37.111-1999",
            "data_format": "FLOAT32",
            "support_status": "SUPPORTED",
            "fixture": "comtrade/ieee_float32/ag_fault.cfg",
        },
        "EVT-SYNTH-CFF-AG": {
            "comtrade_version": "IEEE C37.111-1999",
            "container": "CFF",
            "support_status": "SUPPORTED",
            "fixture": "comtrade/cff/ag_fault.cff",
        },
    }
    import json

    for name, meta in cases.items():
        d = golden / name
        d.mkdir(parents=True, exist_ok=True)
        (d / "expected.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def main() -> None:
    if not SRC_CFG.is_file():
        raise SystemExit(f"Missing source fixture: {SRC_CFG}")
    write_1991()
    write_binary_variants()
    write_cff()
    write_goldens()
    print("Generated COMTRADE golden fixtures under", ROOT)


if __name__ == "__main__":
    main()
