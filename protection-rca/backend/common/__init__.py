"""Shared engineering analysis types and utilities."""

from common.results import SignalResult, not_available, not_calculable, inconclusive
from common.rules_path import resolve_rules_root, resolve_templates_root

__all__ = [
    "SignalResult",
    "not_available",
    "not_calculable",
    "inconclusive",
    "resolve_rules_root",
    "resolve_templates_root",
]
