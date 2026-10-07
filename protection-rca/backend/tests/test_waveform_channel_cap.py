"""Waveform channel selection must not drop trailing protection digitals."""

from __future__ import annotations

from types import SimpleNamespace

from app.services.waveform_service import _select_waveform_channels


def _ch(ctype: str, idx: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(channel_type=ctype, channel_index=idx, name=name)


def test_select_keeps_87g_when_naive_limit_would_drop_it():
    channels = [_ch("ANALOG", i, f"I{i}") for i in range(15)]
    channels += [
        _ch("DIGITAL", i, n)
        for i, n in enumerate(
            [
                "Flag Lost",
                ">Trig.Wave.Cap.",
                "FltRecSta",
                "Relay TRIP",
                "Relay PICKUP",
                "87 picked up",
                "87 BLK 2nd H. A",
                "87 BLK 2nd H. B",
                "87 BLK 2nd H. C",
                "87 BLK nth H. A",
                "87 BLK nth H. B",
                "87 BLK nth H. C",
                "87 TRIP",
                "87 TRIP Phase A",
                "87 TRIP Phase B",
                "87 TRIP Phase C",
                "87-1 TRIP",
                "87-2 TRIP",
                "87G picked up",
                "87G TRIP",
                "87 BLK CWA",
            ]
        )
    ]
    assert len(channels) == 36
    # Old behaviour: LIMIT 32 by ANALOG-then-DIGITAL order dropped 87G
    selected, note = _select_waveform_channels(channels, max_channels=32)
    names = [c.name for c in selected]
    assert "87G picked up" in names
    assert "87G TRIP" in names
    assert len(selected) == 32
    assert note is not None
    # Digitals preferred — some analogs omitted
    assert sum(1 for c in selected if c.channel_type == "DIGITAL") == 21


def test_select_all_when_under_cap():
    channels = [_ch("ANALOG", 0, "IA"), _ch("DIGITAL", 0, "87G picked up")]
    selected, note = _select_waveform_channels(channels, max_channels=128)
    assert len(selected) == 2
    assert note is None
