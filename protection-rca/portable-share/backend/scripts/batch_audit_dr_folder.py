"""Batch-process COMTRADE DRs from a folder via ComtradeService + AnalysisPipeline.

Reports parse failures, pipeline crashes, and likely wrong-processing signals.
"""

from __future__ import annotations

import json
import sys
import traceback
from collections import defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from comtrade import ComtradeService
from app.services.analysis_pipeline import AnalysisPipeline
from protection.channel_ansi import match_ansi_from_channel
from protection.digital_targets import infer_target_role, infer_element_code


ROOT = Path(r"C:\Users\5863.AVAADA\Downloads\DR Files\Files From Bina Mam")
OUT = BACKEND / "scripts" / "_batch_audit_bina_mam.json"


def find_comtrade_pairs(root: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    cfgs = sorted(
        {p.resolve() for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".cfg"}
    )
    for cfg in cfgs:
        dat = None
        for ext in (".dat", ".DAT", ".Dat"):
            cand = cfg.with_suffix(ext)
            if cand.is_file():
                dat = cand
                break
        # case-insensitive sibling search
        if dat is None:
            stem = cfg.stem
            for sib in cfg.parent.iterdir():
                if sib.is_file() and sib.stem == stem and sib.suffix.lower() == ".dat":
                    dat = sib
                    break
        if dat is not None:
            pairs.append((cfg, dat))
        else:
            pairs.append((cfg, Path()))  # missing dat marker
    # ABB REVAL
    for reh in sorted({p.resolve() for p in root.rglob("*") if p.is_file() and p.suffix.lower() == ".reh"}):
        rev = None
        for sib in reh.parent.iterdir():
            if sib.is_file() and sib.stem == reh.stem and sib.suffix.lower() == ".rev":
                rev = sib
                break
        pairs.append((reh, rev or Path()))
    return pairs


def digital_names(record) -> list[str]:
    names: list[str] = []
    dig = getattr(record, "digital_channels", None) or getattr(record, "status_channels", None)
    if dig is None and hasattr(record, "channels"):
        dig = [c for c in record.channels if getattr(c, "is_digital", False) or getattr(c, "channel_type", "") == "digital"]
    if not dig:
        # canonical model variants
        for attr in ("digitals", "digital", "status"):
            dig = getattr(record, attr, None)
            if dig:
                break
    if isinstance(dig, dict):
        return list(dig.keys())
    out = []
    for ch in dig or []:
        if isinstance(ch, str):
            out.append(ch)
        else:
            out.append(str(getattr(ch, "name", None) or getattr(ch, "ch_id", None) or ch))
    return out


def audit_one(cfg: Path, dat: Path) -> dict:
    rel = str(cfg.relative_to(ROOT))
    row: dict = {
        "cfg": rel,
        "status": "ok",
        "issues": [],
        "warnings": [],
        "fault_type": None,
        "fault_status": None,
        "decision": None,
        "n_analog": None,
        "n_digital": None,
        "n_timeline": None,
        "n_protection": None,
        "pickup_els": [],
        "trip_els": [],
        "unknown_role_digitals": [],
        "mapped_els": {},
    }
    if not dat or not dat.is_file():
        row["status"] = "fail"
        row["issues"].append("MISSING_DAT")
        return row

    svc = ComtradeService()
    try:
        ingest = svc.ingest([cfg, dat], validate_after_parse=True)
    except Exception as e:
        row["status"] = "fail"
        row["issues"].append(f"INGEST_EXCEPTION: {type(e).__name__}: {e}")
        row["traceback"] = traceback.format_exc()[-2000:]
        return row

    if not ingest.success or ingest.record is None:
        row["status"] = "fail"
        row["issues"].append("INGEST_FAILED")
        errs = getattr(ingest, "errors", None) or getattr(ingest, "messages", None) or []
        row["ingest_errors"] = [str(x) for x in (errs if isinstance(errs, list) else [errs])]
        # soft notes
        for attr in ("warnings", "limitations", "notes"):
            v = getattr(ingest, attr, None)
            if v:
                row["warnings"].append(f"{attr}={v}")
        return row

    rec = ingest.record
    # channel counts
    analogs = getattr(rec, "analog_channels", None) or getattr(rec, "analogs", None) or []
    dig_names = digital_names(rec)
    if not dig_names:
        # try series keys
        series = getattr(rec, "digital_series", None) or getattr(rec, "status_series", None)
        if isinstance(series, dict):
            dig_names = list(series.keys())
    row["n_analog"] = len(analogs) if not isinstance(analogs, dict) else len(analogs)
    row["n_digital"] = len(dig_names)

    if row["n_analog"] == 0:
        row["issues"].append("NO_ANALOG_CHANNELS")
        row["status"] = "fail"

    role_unknown = []
    mapped = {}
    for name in dig_names:
        role = infer_target_role(name)
        el = infer_element_code(name) or match_ansi_from_channel(name)
        if role == "UNKNOWN":
            role_unknown.append(name)
        if el:
            mapped[name] = el
    row["unknown_role_digitals"] = role_unknown[:40]
    row["mapped_els"] = mapped

    try:
        result = AnalysisPipeline().run(
            rec,
            event_meta={"event_id": rel, "description": rel},
        )
    except Exception as e:
        row["status"] = "fail"
        row["issues"].append(f"PIPELINE_EXCEPTION: {type(e).__name__}: {e}")
        row["traceback"] = traceback.format_exc()[-2000:]
        return row

    fault = result.fault_classification or {}
    row["fault_type"] = fault.get("fault_type") or fault.get("type")
    row["fault_status"] = fault.get("status")
    dec = result.decision or {}
    row["decision"] = dec.get("decision") or dec.get("label") or dec.get("status")
    row["n_timeline"] = len(result.timeline or [])
    row["n_protection"] = len(result.protection_assessment or [])
    row["limitations"] = list(result.limitations or [])[:20]
    if dig_names and len(role_unknown) == len(dig_names) and row["n_protection"] == 0:
        row["warnings"].append("ALL_DIGITALS_ROLE_UNKNOWN")
    if dig_names and not mapped and row["n_protection"] == 0:
        row["warnings"].append("NO_ANSI_MAPPED_FROM_DIGITALS")

    pickups, trips = [], []
    for a in result.protection_assessment or []:
        el = a.get("element") or a.get("element_code")
        actual = (a.get("actual_operation") or "").upper()
        if actual in ("PICKED_UP", "OPERATED", "TRIPPED"):
            pickups.append(f"{el}:{actual}")
        if actual in ("OPERATED", "TRIPPED"):
            trips.append(f"{el}:{actual}")
    row["pickup_els"] = pickups
    row["trip_els"] = trips

    # Heuristic issue flags
    if row["fault_status"] in (None, "UNKNOWN", "UNCLASSIFIED") and row["n_analog"]:
        row["warnings"].append("FAULT_UNCLASSIFIED")
    if row["n_digital"] and row["n_timeline"] == 0:
        row["warnings"].append("DIGITALS_PRESENT_BUT_EMPTY_TIMELINE")
    if row["n_digital"] and row["n_protection"] == 0 and mapped:
        row["warnings"].append("MAPPED_ELEMENTS_BUT_NO_PROTECTION_ROWS")
    # False 50 from bay names pattern already fixed — still flag if assessment has only spurious
    if any(str(k).upper().startswith("50BT") for k in dig_names) and any(
        p.startswith("50:") for p in pickups + trips
    ):
        # only if no real I> style evidence
        if not any("I>" in n or "IN" in n.upper() for n in dig_names):
            row["warnings"].append("POSSIBLE_FALSE_50_FROM_BAY_NAME")

    if row["issues"]:
        row["status"] = "fail"
    elif row["warnings"]:
        row["status"] = "warn"
    return row


def main() -> int:
    pairs = find_comtrade_pairs(ROOT)
    print(f"Found {len(pairs)} CFG records under {ROOT}")
    rows = []
    for i, (cfg, dat) in enumerate(pairs, 1):
        print(f"[{i}/{len(pairs)}] {cfg.relative_to(ROOT)}")
        rows.append(audit_one(cfg, dat))

    summary = {
        "root": str(ROOT),
        "total": len(rows),
        "ok": sum(1 for r in rows if r["status"] == "ok"),
        "warn": sum(1 for r in rows if r["status"] == "warn"),
        "fail": sum(1 for r in rows if r["status"] == "fail"),
        "issue_counts": defaultdict(int),
        "warning_counts": defaultdict(int),
    }
    for r in rows:
        for i in r.get("issues") or []:
            key = i.split(":")[0]
            summary["issue_counts"][key] += 1
        for w in r.get("warnings") or []:
            summary["warning_counts"][w] += 1
    summary["issue_counts"] = dict(summary["issue_counts"])
    summary["warning_counts"] = dict(summary["warning_counts"])

    payload = {"summary": summary, "records": rows}
    OUT.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
