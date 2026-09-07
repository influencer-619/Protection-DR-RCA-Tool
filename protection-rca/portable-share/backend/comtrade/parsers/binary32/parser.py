"""32-bit integer binary COMTRADE DAT parser (BINARY32)."""

from __future__ import annotations

import struct

from comtrade.parsers.ascii.parser import ParsedDat
from comtrade.parsers.common import ParsedCfg
from comtrade.scaling import MISSING_INT32


class Binary32DatParser:
    """Parse little-endian BINARY32 DAT (32-bit analog integers).

    Record layout per sample:
      - int32 sample number
      - int32 timestamp (µs)
      - int32 × Na analog values (0x80000000 = missing)
      - uint16 × ceil(Nd/16) status words
    """

    def parse(self, data: bytes, cfg: ParsedCfg) -> ParsedDat:
        result = ParsedDat()
        for ch in cfg.analog_channels:
            result.analog_raw[ch.name] = []
        for ch in cfg.digital_channels:
            result.digital_raw[ch.name] = []

        n_status_words = (cfg.digital_count + 15) // 16
        record_size = 4 + 4 + 4 * cfg.analog_count + 2 * n_status_words
        if record_size <= 8:
            result.warnings.append("invalid binary32 record size")
            return result

        offset = 0
        sample_idx = 0
        while offset + record_size <= len(data):
            n_val = struct.unpack_from("<i", data, offset)[0]
            ts_val = struct.unpack_from("<i", data, offset + 4)[0]
            pos = offset + 8

            result.sample_numbers.append(n_val)
            result.timestamps.append(int(ts_val))

            for ch in cfg.analog_channels:
                raw = struct.unpack_from("<i", data, pos)[0]
                pos += 4
                if raw == MISSING_INT32:
                    result.analog_raw[ch.name].append(None)
                else:
                    result.analog_raw[ch.name].append(float(raw))

            status_bits: list[int] = []
            for _ in range(n_status_words):
                word = struct.unpack_from("<H", data, pos)[0]
                pos += 2
                for bit in range(16):
                    status_bits.append((word >> bit) & 1)

            for i, ch in enumerate(cfg.digital_channels):
                bit = status_bits[i] if i < len(status_bits) else 0
                result.digital_raw[ch.name].append(bit)

            offset += record_size
            sample_idx += 1

        result.sample_count = sample_idx
        remainder = len(data) - offset
        if remainder:
            result.warnings.append(f"{remainder} trailing byte(s) after last full record")
        if cfg.end_sample and result.sample_count and result.sample_count != cfg.end_sample:
            result.warnings.append(
                f"sample count {result.sample_count} != CFG endsamp {cfg.end_sample}"
            )
        return result
