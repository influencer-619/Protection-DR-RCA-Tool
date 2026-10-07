"""ABB REVAL (.reh / .rev) → CanonicalDisturbanceRecord.

REVAL stores a text header (``*.reh``) and a companion data file (``*.rev``).
Full binary REV decoding varies by RECOM version; this parser always builds a
usable record from REH channel RMS / digital Value= fields and the Event list,
so Mumbai-end style files can enter the same RCA pipeline as COMTRADE.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Sequence

from comtrade.canonical.model import (
    AnalogChannel,
    CanonicalDisturbanceRecord,
    DigitalChannel,
    SampleRateSection,
)


def _paths(files: Sequence[Path]) -> tuple[Optional[Path], Optional[Path]]:
    reh = rev = None
    for f in files:
        p = Path(f)
        suf = p.suffix.lower()
        if suf == ".reh":
            reh = p
        elif suf == ".rev":
            rev = p
    if reh is None:
        for f in files:
            p = Path(f)
            if p.suffix.lower() == ".reh":
                reh = p
                break
    if reh and rev is None:
        cand = reh.with_suffix(".REV")
        if not cand.is_file():
            cand = reh.with_suffix(".rev")
        if cand.is_file():
            rev = cand
    return reh, rev


def is_reval(files: Sequence[Path]) -> bool:
    reh, _ = _paths(files)
    if reh is None:
        return False
    try:
        head = reh.read_text(encoding="latin-1", errors="replace")[:800]
    except OSError:
        return False
    return (
        "AnalogueChannels" in head
        or "RECOM" in head
        or ("Time=" in head and "Trig=" in head and "ttot=" in head)
    )


def _kv(line: str) -> tuple[str, str]:
    line = line.strip()
    if "=" not in line:
        return "", ""
    k, _, rest = line.partition("=")
    v = rest.split("!")[0].strip()
    return k.strip(), v


def parse_reval(files: Sequence[Path]) -> CanonicalDisturbanceRecord:
    reh, rev = _paths(files)
    if reh is None:
        raise ValueError("REVAL parse requires a .reh header file")
    text = reh.read_text(encoding="latin-1", errors="replace")
    meta: dict[str, str] = {}
    analogs: list[dict[str, str]] = []
    digitals: list[dict[str, str]] = []
    events: list[tuple[float, str, int]] = []
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("+") and line.endswith("!"):
            section = line.strip("+!").split()[0] if line.strip("+!") else ""
            continue
        if line.startswith("-") and line.endswith("!"):
            section = ""
            continue
        if section == "AnalogueChannels" and line.startswith("#"):
            # #1,id=U1,InUse=1,...,prRMS=126.000,poRMS=126.000,...
            fields = {}
            for part in line.lstrip("#").split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    fields[k.strip()] = v.strip()
            if fields.get("id"):
                analogs.append(fields)
            continue
        if section == "DigitalChannels" and line.startswith("#"):
            fields = {}
            for part in line.lstrip("#").split(","):
                if "=" in part:
                    k, v = part.split("=", 1)
                    fields[k.strip()] = v.strip()
            if fields.get("id"):
                digitals.append(fields)
            continue
        if section == "Event" and line.startswith("#"):
            # #1,12.51;25.645 GEN TRIP      þOn!
            m = re.match(
                r"#\d+,(\d+)\.(\d+);([\d.]+)\s+(.+?)\s+(?:þ)?(On|Off)!",
                line,
                re.I,
            )
            if m:
                hh, mm, sec, name, state = m.groups()
                t = int(hh) * 3600 + int(mm) * 60 + float(sec)
                events.append((t, name.strip(), 1 if state.lower() == "on" else 0))
            continue
        if "=" in line and section == "":
            k, v = _kv(line)
            if k:
                meta[k] = v

    freq = 50.0
    if meta.get("LFreq") == "1":
        freq = 60.0
    # SampleRate field is "50 percent of low freq" → ×2
    try:
        sr = float(meta.get("SampleRate") or 1000) * 2.0
    except (TypeError, ValueError):
        sr = 2000.0
    try:
        ttot_ms = float(meta.get("ttot") or 1000)
    except (TypeError, ValueError):
        ttot_ms = 1000.0
    n_pre = max(4, int(sr * float(meta.get("tpre") or 300) / 1000.0))
    n_tot = max(n_pre + 4, int(sr * ttot_ms / 1000.0))

    start_time = None
    # Time=31-03- 9,12:51:25.645!
    tm = meta.get("Time") or ""
    m = re.match(r"(\d+)-(\d+)-\s*(\d+),(\d+):(\d+):([\d.]+)", tm)
    if m:
        dd, mo, yy, hh, mi, sec = m.groups()
        year = 2000 + int(yy) if int(yy) < 100 else int(yy)
        try:
            start_time = datetime(
                year, int(mo), int(dd), int(hh), int(mi), int(float(sec)),
                int((float(sec) % 1) * 1e6),
            )
        except ValueError:
            start_time = None

    analog_channels: list[AnalogChannel] = []
    digital_channels: list[DigitalChannel] = []
    scaled: dict[str, list[float]] = {}
    raw: dict[str, list[float]] = {}
    units: dict[str, str] = {}

    for i, fields in enumerate(analogs):
        if fields.get("InUse") == "0":
            continue
        name = fields["id"].strip()
        typ = fields.get("Type", "0")  # 0=V 1=I
        unit = "A" if typ == "1" else "V"
        try:
            pre = float(fields.get("prRMS") or 0)
            post = float(fields.get("poRMS") or pre)
        except (TypeError, ValueError):
            pre = post = 0.0
        series = [pre] * n_pre + [post] * (n_tot - n_pre)
        try:
            prim = float(fields.get("Prim") or 0) or None
            sec = float(fields.get("Sec") or 0) or None
        except (TypeError, ValueError):
            prim = sec = None
        analog_channels.append(
            AnalogChannel(
                index=i + 1,
                name=name,
                phase="",
                unit=unit,
                a=1.0,
                b=0.0,
                primary=prim,
                secondary=sec,
            )
        )
        scaled[name] = series
        raw[name] = series
        units[name] = unit

    for i, fields in enumerate(digitals):
        name = fields["id"].strip()
        try:
            val = int(float(fields.get("Value") or 0))
        except (TypeError, ValueError):
            val = 0
        # Pre-fault low → post-fault Value so timeline sees a rising edge
        series = [0.0] * n_pre + [float(val)] * (n_tot - n_pre)
        # Overlay Event list transitions when timestamps fall in window
        if events:
            t0 = events[0][0]
            for t, ename, state in events:
                if ename.strip().upper() != name.upper():
                    continue
                idx = int(max(0, min(n_tot - 1, (t - t0) * sr)))
                # Ensure edge from 0 before first On
                if state == 1 and idx > 0:
                    for j in range(0, idx):
                        if series[j] == 0:
                            break
                        series[j] = 0.0
                for j in range(idx, n_tot):
                    series[j] = float(state)
        digital_channels.append(
            DigitalChannel(index=i + 1, name=name, normal_state=0)
        )
        scaled[name] = series
        raw[name] = series

    # Map REVAL U1/I1… to phase names for role inference
    rename = {
        "U1": "VA",
        "U2": "VB",
        "U3": "VC",
        "I1": "IA",
        "I2": "IB",
        "I3": "IC",
        "I4": "IN",
    }
    for old, new in list(rename.items()):
        if old in scaled and new not in scaled:
            scaled[new] = scaled[old]
            raw[new] = raw[old]
            units[new] = units.get(old, "A" if new.startswith("I") else "V")
            analog_channels.append(
                AnalogChannel(
                    index=len(analog_channels) + 1,
                    name=new,
                    phase=new[-1] if new[-1] in "ABC" else ("N" if new.endswith("N") else ""),
                    unit=units[new],
                    a=1.0,
                    b=0.0,
                )
            )

    timestamps = [int(i * 1e6 / sr) for i in range(n_tot)]
    quality = {
        "status": "REVAL_HEADER",
        "notes": [
            "Parsed from ABB REVAL .reh (RMS pre/post + digital Value/Event). "
            "Full .rev waveform samples not decoded — convert to COMTRADE in RECOM/HV Collect for high-fidelity analysis."
        ],
    }
    if rev is not None:
        quality["notes"].append(f"Companion REV present: {rev.name} (not fully decoded)")

    # Placeholder epoch / missing clock
    if start_time and start_time.year in (1990, 1991, 1992, 1993, 1994, 1980):
        quality["clock_suspect"] = True
        quality["notes"].append(f"Suspect/default DR clock: {start_time.isoformat()}")

    sources = [str(reh)]
    if rev:
        sources.append(str(rev))

    return CanonicalDisturbanceRecord(
        record_id=reh.stem,
        standard="ABB",
        revision="REVAL",
        container="REH_REV",
        station=meta.get("StationId") or meta.get("ObjectId") or "",
        device=meta.get("UnitId") or meta.get("SrcType") or "",
        nominal_frequency=freq,
        start_time=start_time,
        trigger_time=start_time,
        sample_rates=[SampleRateSection(sample_rate_hz=sr, end_sample=n_tot)],
        analog_channels=analog_channels,
        digital_channels=digital_channels,
        samples=n_tot,
        timestamps=timestamps,
        raw_values=raw,
        scaled_values=scaled,
        units=units,
        quality=quality,
        source_files=sources,
        data_format="REVAL",
        unsupported_features=["reval_rev_binary_not_decoded"],
    )
