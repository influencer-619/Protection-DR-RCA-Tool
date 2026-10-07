"""Storage key suffixes must be safe on Windows (COMTRADE names with '>')."""

from app.services.storage import StorageService
from app.services.waveform_service import _safe_channel_token


def test_safe_key_suffix_strips_siemens_trig_gt():
    s = StorageService.safe_key_suffix(".>trig.wave.cap..json")
    assert ">" not in s
    assert s.endswith(".json")
    key = StorageService.content_key("a" * 64, prefix="waveforms/x", suffix=".>trig.wave.cap..json")
    assert ">" not in key
    assert key.endswith(".json")


def test_safe_channel_token():
    assert _safe_channel_token(">trig.wave.cap.") == "trig.wave.cap"
    assert ">" not in _safe_channel_token("IL1> pickup")
