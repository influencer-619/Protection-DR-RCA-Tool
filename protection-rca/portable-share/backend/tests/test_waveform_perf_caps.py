"""PERF-013 — waveform caps come from settings."""

from __future__ import annotations

from app.core.config import Settings


def test_default_waveform_caps():
    s = Settings()
    assert s.waveform_max_points == 20000
    assert s.waveform_max_channels == 128


def test_settings_accept_env_override(monkeypatch):
    monkeypatch.setenv("WAVEFORM_MAX_POINTS", "5000")
    monkeypatch.setenv("WAVEFORM_MAX_CHANNELS", "64")
    s = Settings()
    assert s.waveform_max_points == 5000
    assert s.waveform_max_channels == 64
