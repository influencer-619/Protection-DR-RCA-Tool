"""Shared COMTRADE CFG parsing utilities (IEEE 1991 / 1999 / 2013)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from comtrade.canonical.model import (
    AnalogChannel,
    DigitalChannel,
    SampleRateSection,
)


@dataclass
class ParsedCfg:
    """Structured result of CFG text parsing."""

    station: str = ""
    device: str = ""
    revision_year: Optional[str] = None
    total_channels: int = 0
    analog_count: int = 0
    digital_count: int = 0
    analog_channels: list[AnalogChannel] = field(default_factory=list)
    digital_channels: list[DigitalChannel] = field(default_factory=list)
    nominal_frequency: float = 50.0
    nrates: int = 1
    sample_rates: list[SampleRateSection] = field(default_factory=list)
    start_time: Optional[datetime] = None
    trigger_time: Optional[datetime] = None
    data_format: str = "ASCII"
    time_multiplier: float = 1.0
    time_code: Optional[str] = None
    local_code: Optional[str] = None
    tmq_code: Optional[str] = None
    leapsec: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)
    end_sample: int = 0  # max endsamp across rate sections


_DATE_RE = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{2,4}),\s*(.+)$"
)
_TIME_RE = re.compile(
    r"^(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?$"
)


def split_csv_line(line: str) -> list[str]:
    """Split a CFG/DAT CSV line, preserving empty fields."""
    return [p.strip() for p in line.rstrip("\r\n").split(",")]


def nonempty_lines(text: str) -> list[str]:
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def parse_comtrade_datetime(line: str) -> Optional[datetime]:
    """Parse ``dd/mm/yyyy,hh:mm:ss.ffffff`` per IEEE C37.111.

    Does **not** swap day/month. Returns None if unparseable.
    """
    m = _DATE_RE.match(line.strip())
    if not m:
        return None
    day_s, month_s, year_s, time_s = m.groups()
    day, month = int(day_s), int(month_s)
    year = int(year_s)
    if year < 100:
        year += 2000 if year < 70 else 1900

    tm = _TIME_RE.match(time_s.strip())
    if not tm:
        return None
    hh, mm, ss, frac = tm.groups()
    micro = 0
    if frac:
        # Pad/truncate to microseconds
        frac_padded = (frac + "000000")[:6]
        micro = int(frac_padded)
    try:
        return datetime(year, month, day, int(hh), int(mm), int(ss), micro)
    except ValueError:
        return None


def _parse_float(value: str, default: float = 0.0) -> float:
    try:
        return float(value) if value != "" else default
    except ValueError:
        return default


def _parse_optional_float(value: str) -> Optional[float]:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _looks_like_analog_channel(parts: list[str]) -> bool:
    """Heuristic: IEEE analog lines have numeric scale factor at field index 5."""
    if len(parts) < 6:
        return False
    try:
        float(parts[0])
        float(parts[5])
        return True
    except (ValueError, IndexError):
        return False


def _looks_like_digital_channel(parts: list[str]) -> bool:
    """Heuristic: digital lines are short and not analog-shaped."""
    if len(parts) < 2 or _looks_like_analog_channel(parts):
        return False
    try:
        float(parts[0])
    except ValueError:
        return False
    # Name present; optional phase/ccbm/y — not a lone frequency token
    if len(parts) == 1:
        return False
    return True


def _looks_like_frequency_line(parts: list[str]) -> bool:
    if not parts or not parts[0]:
        return False
    try:
        freq = float(parts[0])
    except ValueError:
        return False
    return 10.0 <= freq <= 400.0 and len([p for p in parts if p != ""]) <= 1


def parse_analog_line(parts: list[str], warnings: list[str]) -> AnalogChannel:
    """Parse one analog channel definition line.

    1991: An,ch_id,ph,ccbm,uu,a,b,skew,min,max
    1999+: …,primary,secondary,PS

    Some vendor exports (e.g. ABB REF615) omit skew and emit 12 fields:
      An,ch_id,ph,ccbm,uu,a,b,min,max,primary,secondary,PS
    """
    idx = int(float(parts[0])) if parts else 0
    name = parts[1] if len(parts) > 1 else f"A{idx}"
    phase = parts[2] if len(parts) > 2 else ""
    ccbm = parts[3] if len(parts) > 3 else ""
    unit = parts[4] if len(parts) > 4 else ""
    a = _parse_float(parts[5], 1.0) if len(parts) > 5 else 1.0
    b = _parse_float(parts[6], 0.0) if len(parts) > 6 else 0.0

    # Detect omitted skew: 12 fields ending with P/S (1999 without skew),
    # or 13 fields with blank skew slot.
    missing_skew = (
        len(parts) == 12
        and parts[11].upper() in ("P", "S")
        and _parse_optional_float(parts[7]) is not None
        and _parse_optional_float(parts[8]) is not None
    )
    blank_skew = (
        len(parts) >= 13
        and parts[12].upper() in ("P", "S")
        and (parts[7] is None or str(parts[7]).strip() == "")
    )
    if missing_skew or blank_skew:
        warnings.append(
            f"analog ch {idx}: skew omitted (vendor form) — assuming skew=0"
        )
        skew = 0.0
        if missing_skew:
            min_v = _parse_optional_float(parts[7])
            max_v = _parse_optional_float(parts[8])
            primary = _parse_optional_float(parts[9])
            secondary = _parse_optional_float(parts[10])
            ps = parts[11].upper()
        else:
            min_v = _parse_optional_float(parts[8]) if len(parts) > 8 else None
            max_v = _parse_optional_float(parts[9]) if len(parts) > 9 else None
            primary = _parse_optional_float(parts[10]) if len(parts) > 10 else None
            secondary = _parse_optional_float(parts[11]) if len(parts) > 11 else None
            ps = parts[12].upper()
    else:
        skew = _parse_float(parts[7], 0.0) if len(parts) > 7 else 0.0
        min_v = _parse_optional_float(parts[8]) if len(parts) > 8 else None
        max_v = _parse_optional_float(parts[9]) if len(parts) > 9 else None
        primary = _parse_optional_float(parts[10]) if len(parts) > 10 else None
        secondary = _parse_optional_float(parts[11]) if len(parts) > 11 else None
        ps = parts[12].upper() if len(parts) > 12 and parts[12] else "P"

    if ps not in ("P", "S"):
        warnings.append(f"analog ch {idx}: invalid PS '{ps}', defaulting to P")
        ps = "P"
    return AnalogChannel(
        index=idx,
        name=name,
        phase=phase,
        ccbm=ccbm,
        unit=unit,
        a=a,
        b=b,
        skew=skew,
        min_value=min_v,
        max_value=max_v,
        primary=primary,
        secondary=secondary,
        ps=ps,
    )


def parse_digital_line(parts: list[str]) -> DigitalChannel:
    """Parse one digital/status channel line.

    1991: Dn,ch_id[,ph][,y]
    1999+: Dn,ch_id,ph,ccbm,y
    """
    idx = int(float(parts[0])) if parts else 0
    name = parts[1] if len(parts) > 1 else f"D{idx}"
    phase = parts[2] if len(parts) > 2 else ""
    ccbm = parts[3] if len(parts) > 3 else ""
    y = 0
    if len(parts) > 4 and parts[4] != "":
        try:
            y = int(float(parts[4]))
        except ValueError:
            y = 0
    elif len(parts) == 3 and parts[2] in ("0", "1"):
        # 1991 short form: Dn,ch_id,y
        y = int(parts[2])
        phase = ""
    return DigitalChannel(index=idx, name=name, phase=phase, ccbm=ccbm, normal_state=y)


def parse_cfg(text: str) -> ParsedCfg:
    """Parse a full CFG (or CFG section) into :class:`ParsedCfg`.

    Critical IEEE 1999/2013 structure:
      1: station,device,year
      2: TT,##A,##D
      analog lines × Na
      digital lines × Nd
      lf
      nrates
      samp,endsamp  × nrates
      start datetime
      trigger datetime
      ft
      timemult
      [2013] time_code,local_code
      [2013] tmq_code,leapsec
    """
    lines = nonempty_lines(text)
    cfg = ParsedCfg()
    if len(lines) < 2:
        cfg.warnings.append("CFG has fewer than 2 lines")
        return cfg

    # --- Line 1 ---
    p0 = split_csv_line(lines[0])
    cfg.station = p0[0] if p0 else ""
    cfg.device = p0[1] if len(p0) > 1 else ""
    cfg.revision_year = p0[2] if len(p0) > 2 and p0[2] else None

    # --- Line 2: TT,##A,##D ---
    p1 = split_csv_line(lines[1])
    try:
        cfg.total_channels = int(float(p1[0])) if p1 else 0
    except ValueError:
        cfg.warnings.append(f"invalid total channel count: {p1[0] if p1 else ''}")
    for token in p1[1:]:
        t = token.upper().replace(" ", "")
        if t.endswith("A"):
            try:
                cfg.analog_count = int(t[:-1])
            except ValueError:
                cfg.warnings.append(f"invalid analog count token: {token}")
        elif t.endswith("D"):
            try:
                cfg.digital_count = int(t[:-1])
            except ValueError:
                cfg.warnings.append(f"invalid digital count token: {token}")
        elif t.isdigit() and cfg.analog_count == 0:
            # Vendor form: TT,Na,Nd without A/D suffixes (e.g. 8,4,4)
            try:
                cfg.analog_count = int(t)
                # next numeric token becomes Nd if present
                nums = [x for x in p1[1:] if x.replace(".", "", 1).isdigit()]
                if len(nums) >= 2:
                    cfg.digital_count = int(float(nums[1]))
                cfg.warnings.append(
                    f"channel counts without A/D suffixes interpreted as Na={cfg.analog_count}, Nd={cfg.digital_count}"
                )
            except ValueError:
                pass
            break
    if cfg.analog_count + cfg.digital_count != cfg.total_channels and cfg.total_channels:
        cfg.warnings.append(
            f"TT ({cfg.total_channels}) != Na+Nd ({cfg.analog_count}+{cfg.digital_count})"
        )

    idx = 2
    # --- Analog channels (declared Na, then any extra analog-shaped lines) ---
    for _ in range(cfg.analog_count):
        if idx >= len(lines):
            cfg.warnings.append("CFG truncated in analog channel section")
            break
        cfg.analog_channels.append(parse_analog_line(split_csv_line(lines[idx]), cfg.warnings))
        idx += 1
    while idx < len(lines):
        parts = split_csv_line(lines[idx])
        if not _looks_like_analog_channel(parts):
            break
        cfg.warnings.append(
            f"Extra analog channel beyond declared Na={cfg.analog_count} "
            f"(CFG channel-count mismatch — using channel lines as authoritative)"
        )
        cfg.analog_channels.append(parse_analog_line(parts, cfg.warnings))
        idx += 1
    if len(cfg.analog_channels) != cfg.analog_count:
        cfg.warnings.append(
            f"Declared Na={cfg.analog_count} but parsed {len(cfg.analog_channels)} analog channels"
        )
        cfg.analog_count = len(cfg.analog_channels)

    # --- Digital channels ---
    for _ in range(cfg.digital_count):
        if idx >= len(lines):
            cfg.warnings.append("CFG truncated in digital channel section")
            break
        parts = split_csv_line(lines[idx])
        if _looks_like_frequency_line(parts):
            cfg.warnings.append("digital section ended early (frequency line reached)")
            break
        cfg.digital_channels.append(parse_digital_line(parts))
        idx += 1
    while idx < len(lines):
        parts = split_csv_line(lines[idx])
        if _looks_like_frequency_line(parts) or not _looks_like_digital_channel(parts):
            break
        cfg.warnings.append(
            f"Extra digital channel beyond declared Nd={cfg.digital_count} "
            f"(CFG channel-count mismatch — using channel lines as authoritative)"
        )
        cfg.digital_channels.append(parse_digital_line(parts))
        idx += 1
    if len(cfg.digital_channels) != cfg.digital_count:
        cfg.warnings.append(
            f"Declared Nd={cfg.digital_count} but parsed {len(cfg.digital_channels)} digital channels"
        )
        cfg.digital_count = len(cfg.digital_channels)
    cfg.total_channels = cfg.analog_count + cfg.digital_count

    # --- Line frequency ---
    if idx < len(lines):
        cfg.nominal_frequency = _parse_float(split_csv_line(lines[idx])[0], 50.0)
        idx += 1
    else:
        cfg.warnings.append("missing line frequency")

    # --- nrates ---
    if idx < len(lines):
        try:
            cfg.nrates = int(float(split_csv_line(lines[idx])[0]))
        except ValueError:
            cfg.warnings.append(f"invalid nrates: {lines[idx]}")
            cfg.nrates = 1
        idx += 1
    if cfg.nrates > 1:
        cfg.unsupported.append(
            f"nrates={cfg.nrates}: multiple sample-rate sections partially supported"
        )

    # --- samp,endsamp × nrates (+ absorb vendor extra rate lines before datetime) ---
    def _read_rate_line(line: str) -> SampleRateSection | None:
        parts = split_csv_line(line)
        if not parts:
            return None
        # Datetime lines must not be treated as rates
        if parse_comtrade_datetime(line) is not None:
            return None
        try:
            float(parts[0])
        except ValueError:
            return None
        # Reject clear non-rate tokens (ASCII/BINARY/…)
        if parts[0].upper() in ("ASCII", "BINARY", "BINARY32", "FLOAT32"):
            return None
        samp = _parse_float(parts[0], 0.0)
        endsamp = 0
        if len(parts) > 1 and parts[1]:
            try:
                endsamp = int(float(parts[1]))
            except ValueError:
                cfg.warnings.append(f"invalid endsamp '{parts[1]}' in sample-rate line")
                endsamp = 0
        return SampleRateSection(sample_rate_hz=samp, end_sample=endsamp)

    rates_needed = max(cfg.nrates, 1)
    rates_got = 0
    while idx < len(lines) and rates_got < rates_needed:
        rate = _read_rate_line(lines[idx])
        if rate is None:
            break
        # Skip placeholder zero-rate rows some vendors emit before the real samp line
        if rate.sample_rate_hz <= 0 and rates_got == 0:
            cfg.warnings.append(
                f"ignoring zero/invalid sample-rate line before timestamps: {lines[idx]}"
            )
            idx += 1
            continue
        cfg.sample_rates.append(rate)
        cfg.end_sample = max(cfg.end_sample, rate.end_sample)
        rates_got += 1
        idx += 1

    # Absorb additional samp,endsamp lines until a datetime / ft line (ABB quirks)
    while idx < len(lines):
        rate = _read_rate_line(lines[idx])
        if rate is None:
            break
        if rate.sample_rate_hz <= 0:
            cfg.warnings.append(f"ignoring extra invalid sample-rate line: {lines[idx]}")
            idx += 1
            continue
        cfg.warnings.append(
            f"extra sample-rate line beyond nrates={cfg.nrates}: {lines[idx]}"
        )
        # Prefer a positive rate over a prior zero/placeholder
        if cfg.sample_rates and cfg.sample_rates[-1].sample_rate_hz <= 0:
            cfg.sample_rates[-1] = rate
        else:
            cfg.sample_rates.append(rate)
        cfg.end_sample = max(cfg.end_sample, rate.end_sample)
        idx += 1

    if not cfg.sample_rates:
        cfg.warnings.append("no valid sample-rate section found")

    # --- start / trigger datetimes ---
    if idx < len(lines):
        cfg.start_time = parse_comtrade_datetime(lines[idx])
        if cfg.start_time is None:
            cfg.warnings.append(f"unparseable start time: {lines[idx]}")
        idx += 1
    if idx < len(lines):
        cfg.trigger_time = parse_comtrade_datetime(lines[idx])
        if cfg.trigger_time is None:
            cfg.warnings.append(f"unparseable trigger time: {lines[idx]}")
        idx += 1

    # --- ft ---
    if idx < len(lines):
        ft = split_csv_line(lines[idx])[0].upper()
        if ft in ("ASCII", "BINARY", "BINARY32", "FLOAT32"):
            cfg.data_format = ft
        else:
            cfg.warnings.append(f"unrecognized ft '{ft}', defaulting ASCII")
            cfg.data_format = "ASCII"
        idx += 1

    # --- timemult ---
    if idx < len(lines):
        cfg.time_multiplier = _parse_float(split_csv_line(lines[idx])[0], 1.0)
        idx += 1

    # --- 2013 trailers ---
    if idx < len(lines):
        parts = split_csv_line(lines[idx])
        cfg.time_code = parts[0] if parts else None
        cfg.local_code = parts[1] if len(parts) > 1 else None
        idx += 1
    if idx < len(lines):
        parts = split_csv_line(lines[idx])
        cfg.tmq_code = parts[0] if parts else None
        cfg.leapsec = parts[1] if len(parts) > 1 else None
        idx += 1

    return cfg


def new_record_id() -> str:
    return str(uuid.uuid4())
