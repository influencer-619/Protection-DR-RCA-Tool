"""CT saturation and magnetizing-inrush detectors (deterministic, no GenAI)."""

from __future__ import annotations

from typing import Any, Optional

import numpy as np

from electrical_analysis.analyzer import ElectricalAnalysisResult


def _harmonic_ratio(elec: ElectricalAnalysisResult, ch: str, order: int) -> Optional[float]:
    h = elec.harmonics.get(ch)
    if h is None or getattr(h, "status", None) != "OK" or not isinstance(h.value, dict):
        return None
    try:
        nested = h.value.get("harmonics_rms")
        src = nested if isinstance(nested, dict) else h.value
        fund = float(src.get("1") or h.value.get("fundamental_rms") or 0.0)
        harm = float(src.get(str(order)) or 0.0)
    except (TypeError, ValueError):
        return None
    if fund <= 1e-9:
        return None
    return harm / fund


def detect_ct_saturation(
    elec: ElectricalAnalysisResult,
    *,
    second_harmonic_threshold: float = 0.15,
    peak_to_rms_threshold: float = 2.8,
) -> dict[str, Any]:
    """
    Soft CT-saturation indicators from harmonics / crest factor.

    Phase currents only (IA/IB/IC). Neutral / residual (IN, 3I0) often show
    high H2 during earth faults without implying CT saturation — those are excluded.
    Does not declare malfunction — returns NOT_INDICATED when evidence is weak.
    """
    suspects: list[dict[str, Any]] = []
    for ch, role in elec.channel_roles.items():
        ru = str(role).upper().strip()
        # Phase CTs only — skip residual / neutral / ground
        if ru not in ("IA", "IB", "IC", "I"):
            continue
        h2 = _harmonic_ratio(elec, ch, 2)
        peak = elec.peak.get(ch)
        rms = elec.rms.get(ch)
        crest = None
        if (
            peak is not None
            and peak.status == "OK"
            and rms is not None
            and rms.status == "OK"
            and isinstance(peak.value, (int, float))
            and isinstance(rms.value, (int, float))
            and float(rms.value) > 1e-9
        ):
            crest = abs(float(peak.value)) / float(rms.value)

        reasons: list[str] = []
        if h2 is not None and h2 >= second_harmonic_threshold:
            reasons.append(f"H2/H1={h2:.3f} ≥ {second_harmonic_threshold}")
        if crest is not None and crest >= peak_to_rms_threshold:
            reasons.append(f"crest={crest:.2f} ≥ {peak_to_rms_threshold}")
        if reasons:
            suspects.append(
                {
                    "channel": ch,
                    "role": role,
                    "h2_ratio": h2,
                    "crest_factor": crest,
                    "reasons": reasons,
                }
            )

    if not suspects:
        return {
            "status": "NOT_INDICATED",
            "suspects": [],
            "notes": "No phase-CT saturation indicators above thresholds",
        }
    return {
        "status": "POSSIBLE",
        "suspects": suspects,
        "notes": "Soft indicators only — verify with secondary injection / CT magnetizing curve",
    }


def detect_magnetizing_inrush(
    elec: ElectricalAnalysisResult,
    *,
    second_harmonic_threshold: float = 0.20,
    min_channels: int = 1,
) -> dict[str, Any]:
    """Magnetizing inrush often shows elevated 2nd harmonic content in phase currents."""
    hits: list[dict[str, Any]] = []
    for ch, role in elec.channel_roles.items():
        if str(role).upper() not in ("IA", "IB", "IC", "I"):
            continue
        h2 = _harmonic_ratio(elec, ch, 2)
        if h2 is not None and h2 >= second_harmonic_threshold:
            hits.append({"channel": ch, "role": role, "h2_ratio": h2})

    if len(hits) < min_channels:
        return {
            "status": "NOT_INDICATED",
            "channels": hits,
            "notes": "2nd-harmonic inrush signature not indicated",
        }
    return {
        "status": "POSSIBLE",
        "channels": hits,
        "notes": "Elevated H2 suggests magnetizing inrush — confirm against 87T restrain logic",
    }


def waveform_crest_from_series(samples: list[float]) -> Optional[float]:
    if not samples:
        return None
    arr = np.asarray(samples, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return None
    rms = float(np.sqrt(np.mean(np.square(arr))))
    if rms < 1e-12:
        return None
    return float(np.max(np.abs(arr)) / rms)
