"""Deterministic fault classification and distance analysis."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from app.core.enums import ClassificationStatus, FaultType
from common.results import ALGORITHM_VERSION
from electrical_analysis.analyzer import ElectricalAnalysisResult


@dataclass
class FaultClassificationResult:
    fault_type: str
    status: str  # CLASSIFIED | PROBABLE | INCONCLUSIVE | UNKNOWN
    confidence: str
    evidence: dict[str, Any] = field(default_factory=dict)
    distance: dict[str, Any] = field(default_factory=dict)
    limitations: list[str] = field(default_factory=list)
    algorithm_version: str = ALGORITHM_VERSION

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mag(phasor_result) -> Optional[float]:
    if phasor_result is None or phasor_result.status != "OK":
        return None
    if isinstance(phasor_result.value, dict):
        return float(phasor_result.value.get("magnitude", 0.0))
    return None


def _rms_val(rms_result) -> Optional[float]:
    if rms_result is None or rms_result.status != "OK":
        return None
    try:
        return float(rms_result.value)
    except (TypeError, ValueError):
        return None


def _features_from_electrical(elec: ElectricalAnalysisResult) -> dict[str, Any]:
    roles = {v: k for k, v in elec.channel_roles.items()}
    ia = _rms_val(elec.rms.get(roles.get("IA", ""), None)) if roles.get("IA") else None
    ib = _rms_val(elec.rms.get(roles.get("IB", ""), None)) if roles.get("IB") else None
    ic = _rms_val(elec.rms.get(roles.get("IC", ""), None)) if roles.get("IC") else None
    # Prefer end-of-record phasors for faulted state if RMS used whole window —
    # also check sequence components
    seq_i = elec.sequences.get("current_sequences")
    i0 = i2 = None
    if seq_i and seq_i.status == "OK" and isinstance(seq_i.value, dict):
        i0 = seq_i.value.get("zero", {}).get("magnitude")
        i2 = seq_i.value.get("negative", {}).get("magnitude")

    vals = [v for v in (ia, ib, ic) if v is not None]
    if len(vals) < 3 or any(v is None for v in (ia, ib, ic)):
        return {"available": False}

    peak = float(max(vals))
    if peak <= 0:
        return {"available": False}

    # Relative participation: phase is elevated if ≥ 70% of peak phase current.
    # Avoids needing pre-fault baseline when only fault-window RMS is available.
    thr = 0.7 * peak

    def elevated(x: Optional[float]) -> Optional[bool]:
        if x is None:
            return None
        return bool(x >= thr)

    ground = False
    if i0 is not None and peak > 0:
        ground = bool(i0 >= 0.15 * peak)

    return {
        "available": True,
        "Ia": ia,
        "Ib": ib,
        "Ic": ic,
        "Ia_elevated": elevated(ia),
        "Ib_elevated": elevated(ib),
        "Ic_elevated": elevated(ic),
        "I0": i0,
        "I2": i2,
        "ground": ground,
        "threshold": thr,
    }


def _classify_from_features(feat: dict[str, Any]) -> tuple[str, str, str]:
    """Return fault_type, status, confidence."""
    if not feat.get("available"):
        return FaultType.UNKNOWN.value, ClassificationStatus.UNKNOWN.value, "INCONCLUSIVE"

    flags = {
        "A": feat.get("Ia_elevated"),
        "B": feat.get("Ib_elevated"),
        "C": feat.get("Ic_elevated"),
    }
    if any(v is None for v in flags.values()):
        return (
            FaultType.UNKNOWN.value,
            ClassificationStatus.INCONCLUSIVE.value,
            "INCONCLUSIVE",
        )

    elevated = {p for p, v in flags.items() if v}
    ground = bool(feat.get("ground"))

    mapping_noground = {
        frozenset("A"): FaultType.AG if ground else None,  # single phase needs ground
        frozenset("B"): FaultType.BG if ground else None,
        frozenset("C"): FaultType.CG if ground else None,
        frozenset(("A", "B")): FaultType.ABG if ground else FaultType.AB,
        frozenset(("B", "C")): FaultType.BCG if ground else FaultType.BC,
        frozenset(("C", "A")): FaultType.CAG if ground else FaultType.CA,
        frozenset(("A", "B", "C")): FaultType.ABCG if ground else FaultType.ABC,
    }

    if not elevated:
        return (
            FaultType.UNKNOWN.value,
            ClassificationStatus.INCONCLUSIVE.value,
            "LOW",
        )

    key = frozenset(elevated)
    if len(elevated) == 1:
        if not ground:
            return (
                FaultType.UNKNOWN.value,
                ClassificationStatus.INCONCLUSIVE.value,
                "LOW",
            )
        ft = {"A": FaultType.AG, "B": FaultType.BG, "C": FaultType.CG}[next(iter(elevated))]
        return ft.value, ClassificationStatus.CLASSIFIED.value, "MEDIUM"

    ft_enum = mapping_noground.get(key)
    if ft_enum is None:
        return FaultType.UNKNOWN.value, ClassificationStatus.INCONCLUSIVE.value, "LOW"
    # Without strong ground evidence for LLG, mark PROBABLE
    if ground and len(elevated) == 2 and feat.get("I0") is None:
        return ft_enum.value, ClassificationStatus.PROBABLE.value, "MEDIUM"
    return ft_enum.value, ClassificationStatus.CLASSIFIED.value, "MEDIUM"


def distance_scheme_applicable(
    *,
    assessments: Optional[list[Any]] = None,
    line_params: Optional[dict[str, Any]] = None,
) -> bool:
    """True when km / Z1 location messaging is in scope (21 operated or line Z1 supplied)."""
    from fault_analysis.location import normalize_line_params

    line = normalize_line_params(line_params)
    if line.get("positive_sequence_impedance_ohm_per_km") is not None:
        return True
    for a in assessments or []:
        d = a.to_dict() if hasattr(a, "to_dict") else (a if isinstance(a, dict) else {})
        el = str(d.get("element") or "").upper()
        if not (el.startswith("21") or "DISTANCE" in el):
            continue
        op = str(d.get("actual_operation") or "").upper()
        if op == "OPERATED" or d.get("pickup") is True or d.get("trip") is True:
            return True
    return False


def classify_fault(
    elec: ElectricalAnalysisResult,
    *,
    line_params: Optional[dict[str, Any]] = None,
    ct_vt_ratios: Optional[dict[str, Any]] = None,
    relay_settings: Optional[dict[str, Any]] = None,
    assessments: Optional[list[Any]] = None,
    distance_applicable: Optional[bool] = None,
) -> FaultClassificationResult:
    from fault_analysis.location import compute_fault_locations, normalize_line_params

    feat = _features_from_electrical(elec)
    ft, status, conf = _classify_from_features(feat)
    limitations: list[str] = []
    if not feat.get("available"):
        limitations.append("Three-phase current evidence NOT AVAILABLE")

    # relay_settings retained for API compatibility; location uses line + electrical
    _ = relay_settings
    if distance_applicable is None:
        distance_applicable = distance_scheme_applicable(
            assessments=assessments, line_params=line_params
        )

    feat = dict(feat)
    feat["distance_applicable"] = bool(distance_applicable)

    if not distance_applicable:
        # OC / EF / 87 / BF / grid cases: do not surface Z1/km or FAULT DISTANCE noise
        distance = {
            "status": "NOT_APPLICABLE",
            "value_km": None,
            "method": None,
            "unit": "km",
            "loop_source": None,
            "loop_impedance": None,
            "algorithms": [],
            "line_impedance_estimate": {"status": "NOT_APPLICABLE", "source": "not_in_scope"},
            "reason": None,
        }
        feat["location_algorithms"] = []
        feat["line_impedance_estimate"] = distance["line_impedance_estimate"]
    else:
        line = normalize_line_params(line_params)
        distance = compute_fault_locations(
            elec,
            fault_type=ft,
            line_params=line,
            ct_vt_ratios=ct_vt_ratios,
        )
        if distance.get("status") in ("NOT_CALCULABLE", "INCONCLUSIVE") and distance.get("reason"):
            limitations.append(str(distance["reason"]))
        elif distance.get("status") == "NOT_CALCULABLE":
            limitations.append("FAULT DISTANCE: NOT CALCULABLE")
        feat["location_algorithms"] = distance.get("algorithms") or []
        feat["line_impedance_estimate"] = distance.get("line_impedance_estimate") or {}

    return FaultClassificationResult(
        fault_type=ft,
        status=status,
        confidence=conf,
        evidence=feat,
        distance=distance,
        limitations=limitations,
    )


def _fault_distance(
    elec: ElectricalAnalysisResult,
    *,
    line_params: Optional[dict[str, Any]],
    ct_vt_ratios: Optional[dict[str, Any]],
    relay_settings: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Backward-compatible wrapper — prefer compute_fault_locations."""
    from fault_analysis.location import compute_fault_locations

    _ = relay_settings
    return compute_fault_locations(
        elec,
        fault_type="AG",
        line_params=line_params,
        ct_vt_ratios=ct_vt_ratios,
    )
