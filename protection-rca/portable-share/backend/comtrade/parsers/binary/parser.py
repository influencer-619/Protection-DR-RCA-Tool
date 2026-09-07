"""16-bit binary COMTRADE DAT parser (IEEE C37.111 BINARY)."""

from __future__ import annotations

import struct

from comtrade.parsers.ascii.parser import ParsedDat
from comtrade.parsers.common import ParsedCfg
from comtrade.scaling import MISSING_INT16


class BinaryDatParser:
    """Parse little-endian binary DAT (16-bit analog samples).

    Record layout per sample:
      - uint32 sample number
      - int32  timestamp (µs)
      - int16  × Na  analog values (0x8000 = missing)
      - uint16 × ceil(Nd/16) status words (LSB = first digital)
    """

    def parse(self, data: bytes, cfg: ParsedCfg) -> ParsedDat:
        result = ParsedDat()
        for ch in cfg.analog_channels:
            result.analog_raw[ch.name] = []
        for ch in cfg.digital_channels:
            result.digital_raw[ch.name] = []

        n_status_words = (cfg.digital_count + 15) // 16
        record_size = 4 + 4 + 2 * cfg.analog_count + 2 * n_status_words
        if record_size <= 8:
            result.warnings.append("invalid binary record size")
            return result

        offset = 0
        sample_idx = 0
        while offset + record_size <= len(data):
            # sample number: int32; timestamp: int32 µs (per IEEE C37.111)
            n_val = struct.unpack_from("<i", data, offset)[0]
            ts_val = struct.unpack_from("<i", data, offset + 4)[0]
            pos = offset + 8

            result.sample_numbers.append(n_val)
            result.timestamps.append(int(ts_val))

            for ch in cfg.analog_channels:
                raw = struct.unpack_from("<h", data, pos)[0]
                pos += 2
                if raw == MISSING_INT16:
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
