"""ASCII COMTRADE DAT parser."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from comtrade.parsers.common import ParsedCfg, split_csv_line


@dataclass
class ParsedDat:
    """Raw DAT payload before scaling / timestamp normalization."""

    sample_numbers: list[int] = field(default_factory=list)
    timestamps: list[int] = field(default_factory=list)  # as stored (pre-timemult)
    analog_raw: dict[str, list[Optional[float]]] = field(default_factory=dict)
    digital_raw: dict[str, list[int]] = field(default_factory=dict)
    sample_count: int = 0
    warnings: list[str] = field(default_factory=list)


def _looks_like_fractional_seconds(token: str) -> bool:
    """True when token is a decimal time-in-seconds style value (e.g. 0.000200)."""
    t = token.strip()
    if "." not in t:
        return False
    try:
        v = float(t)
    except ValueError:
        return False
    # Typical disturbance records are << 1e6 seconds; µs stamps are usually integers.
    return abs(v) < 1_000_000.0


def _timestamp_to_storage(token: str, *, as_seconds: bool) -> int:
    """Store timestamp for later timemult / normalize-from-start (µs domain)."""
    try:
        v = float(token)
    except ValueError:
        return 0
    if as_seconds:
        return int(round(v * 1_000_000.0))
    return int(round(v))


def _detect_ascii_line_layout(
    n_fields: int,
    *,
    analog_count: int,
    digital_count: int,
    first_token: str,
) -> str:
    """Return ``n_timestamp`` (IEEE) or ``timestamp_only`` (vendor / no sample #).

    IEEE C37.111 ASCII: ``n,timestamp,A…,D…`` → 2+Na+Nd fields.
    Common vendor/export: ``timestamp,A…,D…`` → 1+Na+Nd fields.
    """
    std = 2 + analog_count + digital_count
    ts_only = 1 + analog_count + digital_count
    if n_fields >= std:
        # Ambiguous only if extra columns; prefer IEEE when count allows it.
        # Exception: count matches std but column0 is clearly seconds and column
        # count also equals ts_only+something — not needed for exact std match.
        return "n_timestamp"
    if n_fields >= ts_only:
        return "timestamp_only"
    # Short line: guess from first token
    if _looks_like_fractional_seconds(first_token):
        return "timestamp_only"
    return "n_timestamp"


class AsciiDatParser:
    """Parse ASCII DAT text into per-channel raw series.

    Accepts:
    - IEEE: ``n,timestamp,A1..An,D1..Dd``
    - Vendor: ``timestamp,A1..An,D1..Dd`` (no sample number)
    """

    def parse(self, text: str, cfg: ParsedCfg) -> ParsedDat:
        result = ParsedDat()
        for ch in cfg.analog_channels:
            result.analog_raw[ch.name] = []
        for ch in cfg.digital_channels:
            result.digital_raw[ch.name] = []

        na = cfg.analog_count
        nd = cfg.digital_count
        expected_std = 2 + na + nd
        expected_ts = 1 + na + nd
        layout: Optional[str] = None

        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            parts = split_csv_line(line)
            if len(parts) < 1 + max(na, 1):
                result.warnings.append(f"DAT line {line_no}: too few fields")
                continue

            if layout is None:
                layout = _detect_ascii_line_layout(
                    len(parts),
                    analog_count=na,
                    digital_count=nd,
                    first_token=parts[0],
                )
                if layout == "timestamp_only":
                    result.warnings.append(
                        "ASCII DAT layout: timestamp-first (no sample number); "
                        f"expected IEEE ≥{expected_std} fields, got {len(parts)} "
                        f"(accepting {expected_ts}-field vendor form)"
                    )

            if layout == "timestamp_only":
                if len(parts) < expected_ts:
                    result.warnings.append(
                        f"DAT line {line_no}: expected ≥{expected_ts} fields "
                        f"(timestamp-first), got {len(parts)}"
                    )
                n = result.sample_count + 1
                as_seconds = _looks_like_fractional_seconds(parts[0])
                ts = _timestamp_to_storage(parts[0], as_seconds=as_seconds)
                value_base = 1
            else:
                if len(parts) < expected_std:
                    result.warnings.append(
                        f"DAT line {line_no}: expected ≥{expected_std} fields, got {len(parts)}"
                    )
                try:
                    n = int(float(parts[0]))
                except ValueError:
                    # Recover: treat as timestamp-first mid-file
                    if layout == "n_timestamp" and _looks_like_fractional_seconds(parts[0]):
                        layout = "timestamp_only"
                        result.warnings.append(
                            f"DAT line {line_no}: switched to timestamp-first layout"
                        )
                        n = result.sample_count + 1
                        ts = _timestamp_to_storage(parts[0], as_seconds=True)
                        value_base = 1
                    else:
                        result.warnings.append(f"DAT line {line_no}: bad sample number")
                        continue
                else:
                    if len(parts) < 2:
                        result.warnings.append(f"DAT line {line_no}: missing timestamp")
                        continue
                    ts = _timestamp_to_storage(
                        parts[1],
                        as_seconds=_looks_like_fractional_seconds(parts[1]),
                    )
                    value_base = 2

            result.sample_numbers.append(n)
            result.timestamps.append(ts)

            for i, ch in enumerate(cfg.analog_channels):
                col = value_base + i
                if col >= len(parts) or parts[col] == "":
                    result.analog_raw[ch.name].append(None)
                else:
                    try:
                        result.analog_raw[ch.name].append(float(parts[col]))
                    except ValueError:
                        result.analog_raw[ch.name].append(None)
                        result.warnings.append(
                            f"DAT line {line_no}: non-numeric analog '{ch.name}'"
                        )

            dig_base = value_base + na
            for i, ch in enumerate(cfg.digital_channels):
                col = dig_base + i
                if col >= len(parts) or parts[col] == "":
                    result.digital_raw[ch.name].append(0)
                else:
                    try:
                        result.digital_raw[ch.name].append(int(float(parts[col])))
                    except ValueError:
                        result.digital_raw[ch.name].append(0)

            result.sample_count += 1

        if cfg.end_sample and result.sample_count and result.sample_count != cfg.end_sample:
            result.warnings.append(
                f"sample count {result.sample_count} != CFG endsamp {cfg.end_sample}"
            )
        return result
