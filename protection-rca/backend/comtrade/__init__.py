"""COMTRADE detection, parsing, and validation engine.

Public API for the Protection RCA platform.
"""

from comtrade.base import ComtradeParser
from comtrade.canonical.model import (
    AnalogChannel,
    CanonicalDisturbanceRecord,
    DigitalChannel,
    SampleRateSection,
)
from comtrade.detector.service import ComtradeDetectionService, DetectionResult
from comtrade.parsers.registry import ComtradeParserRegistry
from comtrade.quality import QualityAssessment, QualityEngine
from comtrade.scaling import ScalingEngine
from comtrade.service import ComtradeIngestResult, ComtradeService
from comtrade.timestamps import TimestampAssessment, TimestampEngine
from comtrade.validator import ComtradeValidator, ValidationResult

__all__ = [
    "AnalogChannel",
    "CanonicalDisturbanceRecord",
    "ComtradeDetectionService",
    "ComtradeIngestResult",
    "ComtradeParser",
    "ComtradeParserRegistry",
    "ComtradeService",
    "ComtradeValidator",
    "DetectionResult",
    "DigitalChannel",
    "QualityAssessment",
    "QualityEngine",
    "SampleRateSection",
    "ScalingEngine",
    "TimestampAssessment",
    "TimestampEngine",
    "ValidationResult",
]

__version__ = "1.0.0"
