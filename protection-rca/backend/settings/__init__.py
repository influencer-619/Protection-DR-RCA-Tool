"""Settings management subsystem."""

from settings.hierarchy import (
    SettingRecord,
    SettingResolution,
    SettingSource,
    VerificationStatus,
    resolve_setting,
)

__all__ = [
    "SettingRecord",
    "SettingResolution",
    "SettingSource",
    "VerificationStatus",
    "resolve_setting",
]
