"""Blocking IEC 61850 acquisition steps (run in a worker thread)."""

from __future__ import annotations

import csv
import io
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import PurePosixPath
from typing import Any, Optional

from app.services.file_service import infer_source_type
from app.services.iec61850.client import FileEntry, Iec61850Error, MmsSession, split_ln_name
from app.services.iec61850.settings_map import build_settings_document, element_for
from app.services.iec61850.vendors import VendorProfile, detect_profile, get_profile, search_dirs

DR_EXTS = {".cfg", ".dat", ".hdr", ".inf", ".cff", ".cev"}
SCL_EXTS = {".cid", ".icd", ".scd", ".iid", ".ssd"}
SETTINGS_EXTS = {".set", ".rdb", ".xrio", ".rio"}
EVENT_EXTS = {".txt", ".log", ".csv", ".eve", ".xml"}

STATUS_DOS = ("Str", "Op", "Tr")


@dataclass
class Connection:
    host: str
    port: int = 102
    profile_id: str = "AUTO"
    connect_timeout_s: float = 10.0
    request_timeout_s: float = 20.0
    # Engineer override — same idea as ABB 800xA / Elipse “COMTRADE path on device”
    remote_directory: Optional[str] = None

    def session(self) -> MmsSession:
        return MmsSession(
            self.host,
            self.port,
            connect_timeout_s=self.connect_timeout_s,
            request_timeout_s=self.request_timeout_s,
        )

    def dir_hints(self) -> list[str]:
        return [self.remote_directory] if self.remote_directory else []


@dataclass
class Payload:
    filename: str
    data: bytes
    remote_path: Optional[str] = None
    source_type: Optional[str] = None


@dataclass
class AcquireResult:
    records: dict[str, list[Payload]] = field(default_factory=dict)
    record_times: dict[str, Optional[str]] = field(default_factory=dict)
    shared: list[Payload] = field(default_factory=list)
    nameplate: dict[str, Optional[str]] = field(default_factory=dict)
    profile: Optional[VendorProfile] = None
    warnings: list[str] = field(default_factory=list)


def _record_key(path: str) -> str:
    p = PurePosixPath(path.lower())
    return str(p.with_suffix(""))


def classify(entries: list[FileEntry]) -> dict[str, Any]:
    records: dict[str, dict[str, Any]] = {}
    settings: list[FileEntry] = []
    events: list[FileEntry] = []
    scl: list[FileEntry] = []
    for e in entries:
        ext = PurePosixPath(e.basename.lower()).suffix
        src = infer_source_type(e.basename, ext)
        if ext in SCL_EXTS:
            scl.append(e)
        elif src == "SETTINGS" or ext in SETTINGS_EXTS:
            settings.append(e)
        elif ext in DR_EXTS:
            key = _record_key(e.path)
            rec = records.setdefault(
                key,
                {"key": key, "name": PurePosixPath(e.path).stem, "directory": str(PurePosixPath(e.path).parent), "files": []},
            )
            rec["files"].append(e)
        elif ext in EVENT_EXTS:
            events.append(e)

    out_records = []
    for rec in records.values():
        exts = {PurePosixPath(f.basename.lower()).suffix for f in rec["files"]}
        mtime = max((f.last_modified_ms for f in rec["files"]), default=0)
        out_records.append(
            {
                "key": rec["key"],
                "name": rec["name"],
                "directory": rec["directory"],
                "files": sorted(f.path for f in rec["files"]),
                "size": sum(f.size for f in rec["files"]),
                "last_modified_ms": mtime,
                "last_modified": FileEntry("", 0, mtime).last_modified_iso,
                "complete": ".cff" in exts or ".cev" in exts or {".cfg", ".dat"} <= exts,
            }
        )
    out_records.sort(key=lambda r: (r["last_modified_ms"], r["name"]), reverse=True)
    return {"records": out_records, "settings_files": settings, "event_files": events, "scl_files": scl}


def _file_dict(e: FileEntry) -> dict[str, Any]:
    return {"path": e.path, "name": e.basename, "size": e.size, "last_modified": e.last_modified_iso}


def _resolve_profile(conn: Connection, nameplate: dict[str, Optional[str]]) -> VendorProfile:
    if conn.profile_id and conn.profile_id.upper() != "AUTO":
        return get_profile(conn.profile_id)
    return detect_profile(nameplate)


def identify(conn: Connection) -> dict[str, Any]:
    t0 = time.monotonic()
    with conn.session() as s:
        lds = s.logical_devices()
        nameplate = s.nameplate(lds)
        profile = _resolve_profile(conn, nameplate)
        file_service = True
        file_error = None
        try:
            s.list_dir("/")
        except Iec61850Error as exc:
            file_service = False
            file_error = str(exc)
    return {
        "host": conn.host,
        "port": conn.port,
        "logical_devices": lds,
        "nameplate": nameplate,
        "detected_profile": profile.id,
        "detected_profile_label": profile.label,
        "file_service": file_service,
        "file_service_error": file_error,
        "elapsed_ms": int((time.monotonic() - t0) * 1000),
    }


def browse(conn: Connection, *, time_budget_s: float = 90.0) -> dict[str, Any]:
    deadline = time.monotonic() + time_budget_s
    profile: VendorProfile
    dirs: list[str]
    with conn.session() as s:
        lds = s.logical_devices()
        nameplate = s.nameplate(lds)
        profile = _resolve_profile(conn, nameplate)
        dirs = search_dirs(profile, extra=conn.dir_hints())
        entries = s.walk(dirs, deadline=deadline)
    c = classify(entries)
    discovered = sorted(
        {
            str(r["directory"] or "/")
            for r in c["records"]
            if r.get("directory") is not None
        }
    )
    return {
        "nameplate": nameplate,
        "logical_devices": lds,
        "profile": profile.id,
        "profile_label": profile.label,
        "profile_notes": profile.notes,
        "remote_directory": conn.remote_directory,
        "searched_dirs": dirs,
        "discovered_dirs": discovered,
        "records": c["records"],
        "settings_files": [_file_dict(e) for e in c["settings_files"]],
        "event_files": [_file_dict(e) for e in c["event_files"]],
        "scl_files": [_file_dict(e) for e in c["scl_files"]],
        "truncated": time.monotonic() > deadline,
    }


def _read_settings_and_status(
    s: MmsSession, lds: list[str], deadline: float
) -> tuple[dict[str, dict[str, Any]], dict[str, Any], list[dict[str, Any]], Optional[int], list[str]]:
    ln_settings: dict[str, dict[str, Any]] = {}
    behaviour: dict[str, Any] = {}
    status_rows: list[dict[str, Any]] = []
    active_group: Optional[int] = None
    errors: list[str] = []

    for ld in lds:
        try:
            fcs = s.ln_fcs(ld)
        except Iec61850Error as exc:
            errors.append(str(exc))
            continue
        if active_group is None and "SP" in fcs.get("LLN0", set()):
            try:
                sgcb = s.read_fc(f"{ld}/LLN0.SGCB", "SP")
                active_group = sgcb.get("ActSG")
            except Iec61850Error:
                pass
        for ln, ln_fc in sorted(fcs.items()):
            if time.monotonic() > deadline:
                errors.append("Time budget reached — remaining logical nodes not read")
                return ln_settings, behaviour, status_rows, active_group, errors
            _prefix, cls, _inst = split_ln_name(ln)
            if not (cls[:1] in ("P", "R") or cls in ("TCTR", "TVTR", "XCBR")):
                continue
            ref = f"{ld}/{ln}"
            merged: dict[str, Any] = {}
            for fc in ("SP", "SG", "CF") if cls in ("TCTR", "TVTR") else ("SP", "SG"):
                if fc not in ln_fc:
                    continue
                try:
                    merged.update({k: v for k, v in s.read_fc(ref, fc).items() if k not in merged})
                except Iec61850Error as exc:
                    errors.append(str(exc))
            if merged:
                ln_settings[ref] = merged
            if "ST" in ln_fc:
                try:
                    st = s.read_fc(ref, "ST")
                except Iec61850Error as exc:
                    errors.append(str(exc))
                    continue
                if "Beh.stVal" in st:
                    behaviour[ref] = st["Beh.stVal"]
                element = element_for(ln, {k.split(".")[0] for k in merged}) or cls
                for do in STATUS_DOS:
                    t = st.get(f"{do}.t")
                    if t and f"{do}.general" in st:
                        status_rows.append(
                            {"t": t, "tag": f"{ln}.{do}", "desc": f"{element} {do} ({ref})", "state": "ON" if st[f"{do}.general"] else "OFF"}
                        )
                if cls == "XCBR" and st.get("Pos.t"):
                    pos = st.get("Pos.stVal")
                    state = {0: "INTERMEDIATE", 1: "OPEN", 2: "CLOSED", 3: "BAD"}.get(pos if isinstance(pos, int) else -1, str(pos))
                    status_rows.append({"t": st["Pos.t"], "tag": f"{ln}.Pos", "desc": f"Breaker position ({ref})", "state": state})
    return ln_settings, behaviour, status_rows, active_group, errors


def _soe_csv(rows: list[dict[str, Any]], ied_label: str) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["Timestamp", "Event_ID", "IED", "Point_Tag", "Description", "State"])
    for r in sorted(rows, key=lambda x: x["t"]):
        ts = datetime.fromisoformat(r["t"]).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        w.writerow([ts, "", ied_label, r["tag"], r["desc"], r["state"]])
    return buf.getvalue().encode("utf-8")


_CFG_TIME = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})\s*,\s*(\d{1,2}):(\d{2}):(\d{2}(?:\.\d+)?)")


def cfg_trigger_time(cfg: bytes) -> Optional[str]:
    """Trigger timestamp from a COMTRADE CFG (dd/mm/yyyy for 1999+, mm/dd/yy for 1991)."""
    try:
        text = cfg.decode("latin-1")
    except Exception:  # noqa: BLE001
        return None
    lines = text.splitlines()
    rev_1991 = bool(lines) and len(lines[0].split(",")) < 3
    stamps = []
    for line in lines:
        m = _CFG_TIME.match(line)
        if m:
            stamps.append(m.groups())
    if not stamps:
        return None
    a, b, y, hh, mm, ss = stamps[1] if len(stamps) > 1 else stamps[0]
    day, month = (int(b), int(a)) if rev_1991 else (int(a), int(b))
    year = int(y) + (2000 if len(y) == 2 else 0)
    sec = float(ss)
    try:
        dt = datetime(year, month, day, int(hh), int(mm), int(sec), int(round((sec % 1) * 1e6)) % 1_000_000, tzinfo=timezone.utc)
    except ValueError:
        return None
    return dt.isoformat()


def acquire(
    conn: Connection,
    *,
    record_keys: list[str],
    include_settings: bool,
    include_events: bool,
    include_scl: bool,
    ied_label: str,
    allowed_exts: set[str],
    max_bytes: int,
    time_budget_s: float = 240.0,
) -> AcquireResult:
    deadline = time.monotonic() + time_budget_s
    res = AcquireResult()
    wanted = {k.lower() for k in record_keys}

    def grab(e: FileEntry) -> Optional[Payload]:
        ext = PurePosixPath(e.basename.lower()).suffix
        if ext not in allowed_exts:
            res.warnings.append(f"Skipped {e.path}: extension {ext} not allowed")
            return None
        try:
            return Payload(filename=e.basename, data=s.download(e.name, max_bytes=max_bytes), remote_path=e.path)
        except Iec61850Error as exc:
            res.warnings.append(str(exc))
            return None

    with conn.session() as s:
        lds = s.logical_devices()
        res.nameplate = s.nameplate(lds)
        res.profile = _resolve_profile(conn, res.nameplate)
        entries = s.walk(search_dirs(res.profile, extra=conn.dir_hints()), deadline=deadline)
        c = classify(entries)
        by_path = {e.path: e for e in entries}

        for rec in c["records"]:
            if rec["key"] not in wanted:
                continue
            payloads = [p for p in (grab(by_path[f]) for f in rec["files"]) if p]
            if payloads:
                res.records[rec["key"]] = payloads
                cfg = next((p for p in payloads if p.filename.lower().endswith(".cfg")), None)
                res.record_times[rec["key"]] = (cfg_trigger_time(cfg.data) if cfg else None) or rec["last_modified"]
        missing = wanted - set(res.records)
        for key in sorted(missing):
            res.warnings.append(f"Record {key} not found on the IED or could not be downloaded")

        if include_settings:
            for e in c["settings_files"]:
                p = grab(e)
                if p:
                    res.shared.append(p)
        if include_scl:
            for e in c["scl_files"]:
                p = grab(e)
                if p:
                    p.source_type = "ATTACHMENT"
                    res.shared.append(p)
        if include_events:
            for e in c["event_files"]:
                p = grab(e)
                if p:
                    res.shared.append(p)

        if include_settings or include_events:
            ln_settings, behaviour, status_rows, active_group, errors = _read_settings_and_status(s, lds, deadline)
            res.warnings.extend(errors[:20])
            safe_tag = re.sub(r"[^A-Za-z0-9_-]+", "_", ied_label).strip("_") or "IED"
            if include_settings and ln_settings:
                doc = build_settings_document(
                    ied_label=ied_label,
                    host=conn.host,
                    port=conn.port,
                    nameplate=res.nameplate,
                    ln_settings=ln_settings,
                    behaviour=behaviour,
                    active_group=active_group,
                    read_errors=errors,
                )
                res.shared.append(
                    Payload(
                        filename=f"iec61850_settings_{safe_tag}.json",
                        data=json.dumps(doc, indent=2, default=str).encode("utf-8"),
                        source_type="SETTINGS",
                    )
                )
            if include_events and status_rows:
                res.shared.append(
                    Payload(
                        filename=f"iec61850_soe_{safe_tag}.csv",
                        data=_soe_csv(status_rows, ied_label),
                        source_type="SOE",
                    )
                )
    return res
