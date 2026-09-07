"""Analog channel scaling engine for COMTRADE values."""

from __future__ import annotations

from typing import Optional, Sequence

from comtrade.canonical.model import AnalogChannel


# Sentinel used in COMTRADE binary formats for missing samples
MISSING_INT16 = -32768  # 0x8000 as signed
MISSING_INT32 = -2147483648  # 0x80000000 as signed


class ScalingEngine:
    """Apply COMTRADE ``value = (raw * a) + b`` scaling.

    Optionally converts between primary and secondary using the channel's
    ``primary`` / ``secondary`` ratio and ``ps`` preference.
    Missing samples are preserved as ``None`` (never fabricated).
    """

    def scale_sample(
        self,
        raw: Optional[float],
        channel: AnalogChannel,
        *,
        apply_ps: bool = True,
        target_side: Optional[str] = None,
    ) -> Optional[float]:
        """Scale a single raw analog value.

        Parameters
        ----------
        raw:
            Raw DAT value, or ``None`` for a missing sample.
        channel:
            Channel definition with ``a``, ``b``, ``primary``, ``secondary``, ``ps``.
        apply_ps:
            If True, convert toward ``target_side`` (or channel ``ps``).
        target_side:
            ``\"P\"`` or ``\"S\"``. Defaults to channel ``ps``.
        """
        if raw is None:
            return None

        value = (float(raw) * float(channel.a)) + float(channel.b)

        if apply_ps and channel.primary is not None and channel.secondary is not None:
            if abs(channel.secondary) < 1e-15:
                # Cannot convert; leave secondary-referenced value as-is
                return value
            ratio = float(channel.primary) / float(channel.secondary)
            side = (target_side or channel.ps or "P").upper()
            recorded = (channel.ps or "P").upper()
            if side == "P" and recorded == "S":
                value *= ratio
            elif side == "S" and recorded == "P":
                value /= ratio
            # If sides match, values are already on the desired side

        return value

    def scale_channel(
        self,
        raw_values: Sequence[Optional[float]],
        channel: AnalogChannel,
        *,
        apply_ps: bool = True,
        target_side: Optional[str] = None,
    ) -> list[Optional[float]]:
        """Scale an entire channel series."""
        return [
            self.scale_sample(v, channel, apply_ps=apply_ps, target_side=target_side)
            for v in raw_values
        ]

    def scale_all(
        self,
        raw_by_channel: dict[str, Sequence[Optional[float]]],
        channels: Sequence[AnalogChannel],
        *,
        apply_ps: bool = True,
        target_side: Optional[str] = None,
    ) -> dict[str, list[Optional[float]]]:
        """Scale all analog channels keyed by channel name."""
        by_name = {ch.name: ch for ch in channels}
        out: dict[str, list[Optional[float]]] = {}
        for name, series in raw_by_channel.items():
            ch = by_name.get(name)
            if ch is None:
                out[name] = [None if v is None else float(v) for v in series]
            else:
                out[name] = self.scale_channel(
                    series, ch, apply_ps=apply_ps, target_side=target_side
                )
        return out

    @staticmethod
    def is_missing_int16(raw: int) -> bool:
        return int(raw) == MISSING_INT16

    @staticmethod
    def is_missing_int32(raw: int) -> bool:
        return int(raw) == MISSING_INT32
