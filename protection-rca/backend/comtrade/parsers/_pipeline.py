"""Assemble CanonicalDisturbanceRecord from ParsedCfg + ParsedDat."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from comtrade.canonical.model import CanonicalDisturbanceRecord
from comtrade.parsers.ascii.parser import (
    AsciiDatParser,
    ParsedDat,
)
from comtrade.parsers.binary.parser import BinaryDatParser
from comtrade.parsers.binary32.parser import Binary32DatParser
from comtrade.parsers.common import ParsedCfg, new_record_id, parse_cfg
from comtrade.parsers.float32.parser import Float32DatParser
from comtrade.quality import QualityEngine
from comtrade.scaling import ScalingEngine
from comtrade.timestamps import TimestampEngine


class RecordBuilder:
    """Shared CFG+DAT → canonical record pipeline."""

    def __init__(self) -> None:
        self.ascii_parser = AsciiDatParser()
        self.binary_parser = BinaryDatParser()
        self.binary32_parser = Binary32DatParser()
        self.float32_parser = Float32DatParser()
        self.scaling = ScalingEngine()
        self.timestamps = TimestampEngine()
        self.quality = QualityEngine(self.timestamps)

    def parse_dat(self, cfg: ParsedCfg, *, dat_text: Optional[str] = None, dat_bytes: Optional[bytes] = None) -> ParsedDat:
        fmt = cfg.data_format.upper()
        if fmt == "ASCII":
            if dat_text is None:
                if dat_bytes is not None:
                    dat_text = dat_bytes.decode("utf-8", errors="replace")
                else:
                    raise ValueError("ASCII DAT requires text content")
            return self.ascii_parser.parse(dat_text, cfg)
        if dat_bytes is None:
            raise ValueError(f"{fmt} DAT requires binary content")
        if fmt == "BINARY":
            return self.binary_parser.parse(dat_bytes, cfg)
        if fmt == "BINARY32":
            return self.binary32_parser.parse(dat_bytes, cfg)
        if fmt == "FLOAT32":
            return self.float32_parser.parse(dat_bytes, cfg)
        raise ValueError(f"unsupported data format: {fmt}")

    def build(
        self,
        cfg: ParsedCfg,
        dat: ParsedDat,
        *,
        standard: str,
        revision: str,
        container: str,
        source_files: Sequence[str],
        parser_version: str = "1.0.0",
        extra_unsupported: Optional[list[str]] = None,
    ) -> CanonicalDisturbanceRecord:
        rate = cfg.sample_rates[0].sample_rate_hz if cfg.sample_rates else None
        ts_assessment = self.timestamps.assess(
            dat.timestamps,
            timemult=cfg.time_multiplier,
            sample_rate_hz=rate,
        )
        normalized_ts = ts_assessment.normalized_us

        # Scale analogs
        scaled = self.scaling.scale_all(dat.analog_raw, cfg.analog_channels)

        raw_values: dict[str, list] = {}
        raw_values.update({k: list(v) for k, v in dat.analog_raw.items()})
        raw_values.update({k: list(v) for k, v in dat.digital_raw.items()})

        units = {ch.name: ch.unit for ch in cfg.analog_channels}
        channel_metadata = {
            "analog": [
                {
                    "index": ch.index,
                    "name": ch.name,
                    "phase": ch.phase,
                    "ccbm": ch.ccbm,
                    "a": ch.a,
                    "b": ch.b,
                    "skew": ch.skew,
                    "min": ch.min_value,
                    "max": ch.max_value,
                    "primary": ch.primary,
                    "secondary": ch.secondary,
                    "ps": ch.ps,
                }
                for ch in cfg.analog_channels
            ],
            "digital": [
                {
                    "index": ch.index,
                    "name": ch.name,
                    "phase": ch.phase,
                    "ccbm": ch.ccbm,
                    "normal_state": ch.normal_state,
                }
                for ch in cfg.digital_channels
            ],
        }

        unsupported = list(cfg.unsupported)
        if extra_unsupported:
            unsupported.extend(extra_unsupported)

        record = CanonicalDisturbanceRecord(
            record_id=new_record_id(),
            standard=standard,
            revision=revision,
            container=container,
            station=cfg.station,
            device=cfg.device,
            nominal_frequency=cfg.nominal_frequency,
            start_time=cfg.start_time,
            trigger_time=cfg.trigger_time,
            sample_rates=list(cfg.sample_rates),
            analog_channels=list(cfg.analog_channels),
            digital_channels=list(cfg.digital_channels),
            samples=dat.sample_count,
            timestamps=normalized_ts,
            raw_values=raw_values,
            scaled_values={k: list(v) for k, v in scaled.items()},
            units=units,
            channel_metadata=channel_metadata,
            source_files=list(source_files),
            parser_version=parser_version,
            data_format=cfg.data_format,
            time_multiplier=cfg.time_multiplier,
            time_code=cfg.time_code,
            local_code=cfg.local_code,
            tmq_code=cfg.tmq_code,
            leapsec=cfg.leapsec,
            unsupported_features=unsupported,
        )

        # Attach quality (non-mutating assessment stored on record)
        qa = self.quality.assess(record)
        record.quality = qa.to_dict()
        if cfg.warnings or dat.warnings:
            record.quality["cfg_warnings"] = list(cfg.warnings)
            record.quality["dat_warnings"] = list(dat.warnings)
        return record

    def parse_cfg_dat_files(
        self,
        cfg_path: Path,
        dat_path: Path,
        *,
        standard: str,
        revision: str,
        cfg_text: Optional[str] = None,
    ) -> CanonicalDisturbanceRecord:
        from comtrade._io import read_bytes, read_text_lossy

        text = cfg_text if cfg_text is not None else read_text_lossy(cfg_path)
        cfg = parse_cfg(text)
        if cfg.data_format == "ASCII":
            dat = self.parse_dat(cfg, dat_text=read_text_lossy(dat_path))
        else:
            dat = self.parse_dat(cfg, dat_bytes=read_bytes(dat_path))
        return self.build(
            cfg,
            dat,
            standard=standard,
            revision=revision,
            container="CFG_DAT",
            source_files=[str(cfg_path), str(dat_path)],
        )
