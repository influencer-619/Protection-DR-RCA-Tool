"""Abstract COMTRADE parser interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Sequence, Union

from comtrade.canonical.model import CanonicalDisturbanceRecord

FilePath = Union[str, Path]
FileList = Sequence[FilePath]


class ComtradeParser(ABC):
    """Abstract base for all COMTRADE parsers.

    Implementations must:
    - detect format from file *contents* (not extension alone)
    - parse into a :class:`CanonicalDisturbanceRecord`
    - validate without silently repairing data
    """

    PARSER_VERSION: str = "1.0.0"

    @abstractmethod
    def detect(self, files: FileList) -> dict:
        """Inspect files and return a detection summary dict.

        Expected keys include at least: ``standard``, ``revision``,
        ``container``, ``data_format``, ``confidence``, ``status``.
        """

    @abstractmethod
    def parse(self, files: FileList) -> CanonicalDisturbanceRecord:
        """Parse COMTRADE files into a canonical disturbance record."""

    @abstractmethod
    def validate(self, record: CanonicalDisturbanceRecord) -> dict:
        """Validate a parsed record. Never silently repair.

        Returns a dict with ``status`` and ``issues`` (list of finding dicts).
        """
