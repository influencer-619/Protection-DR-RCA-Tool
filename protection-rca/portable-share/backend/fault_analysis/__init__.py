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
    from common.units import normalize_unit

    roles = {v: k for k, v in elec.channel_roles.items()}
    ia_ch = roles.get("IA", "")
    ib_ch = roles.get("IB", "")
    ic_ch = roles.get("IC", "")
    ia = _rms_val(elec.rms.get(ia_ch, None)) if ia_ch else None
    ib = _rms_val(elec.rms.get(ib_ch, None)) if ib_ch else None
    ic = _rms_val(elec.rms.get(ic_ch, None)) if ic_ch else None
    # Prefer end-of-record phasors for faulted state if RMS used whole window —
    # also check sequence components
    seq_i = elec.sequences.get("current_sequences")
    i0 = i2 = None
    current_unit = "A"
    if seq_i and seq_i.status == "OK" and isinstance(seq_i.value, dict):
        i0 = seq_i.value.get("zero", {}).get("magnitude")
        i2 = seq_i.value.get("negative", {}).get("magnitude")
        current_unit = normalize_unit(getattr(seq_i, "unit", None) or "", role="I") or "A"
    for ch in (ia_ch, ib_ch, ic_ch):
        rms = elec.rms.get(ch) if ch else None
        if rms is not None and getattr(rms, "unit", None):
            current_unit = normalize_unit(rms.unit, role="I") or current_unit
            break

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
        "current_unit": current_unit,
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


def _line_z_usable(line_params: Optional[dict[str, Any]]) -> bool:
    """True when verified-enough Z1/km inputs exist for optional location."""
    if not isinstance(line_params, dict) or not line_params:
        return False
    z1 = line_params.get("positive_sequence_impedance_ohm_per_km")
    if not isinstance(z1, dict):
        z1 = line_params.get("z1_ohm_per_km")
    if not isinstance(z1, dict):
        return False
    try:
        x = float(z1.get("X") if z1.get("X") is not None else z1.get("x") or 0)
        length = float(line_params.get("length_km") or line_params.get("length") or 0)
    except (TypeError, ValueError):
        return False
    return abs(x) > 0 and length > 0


def _settings_distance_enabled(relay_settings: Optional[dict[str, Any]]) -> bool:
    """Detect 21 / distance present in relay settings (backup or primary)."""
    if not isinstance(relay_settings, dict):
        return False
    for key, val in relay_settings.items():
        ku = str(key).upper().replace(" ", "")
        if ku.startswith("21") or "DISTANCE" in ku:
            if isinstance(val, dict) and val.get("enabled") is False:
                continue
            return True
    return False


def distance_scheme_applicable(
    *,
    assessments: Optional[list[Any]] = None,
    line_params: Optional[dict[str, Any]] = None,
    relay_settings: Optional[dict[str, Any]] = None,
) -> bool:
    """True when km / Z1 location is in scope.

    Industry practice (e.g. SEL 87L21 / 87L21P): line differential is often
    primary with stepped/piloted distance enabled as backup. Therefore:

    - 21 operated → applicable
    - 21 enabled (backup) with differential → applicable even if 87 tripped first
    - 87L + usable line Z1 → applicable (line location inputs exist)
    - Pure 87B / 87T / 87G without 21 → NOT applicable (bus/xfmr/gen zone)
    - Pure OC/EF without 21 → NOT applicable (line Z1 alone does not unlock)
    """

    def _row(a: Any) -> dict[str, Any]:
        if hasattr(a, "to_dict"):
            return a.to_dict()
        return a if isinstance(a, dict) else {}

    def _operated(d: dict[str, Any]) -> bool:
        op = str(d.get("actual_operation") or "").upper()
        return op == "OPERATED" or d.get("pickup") is True or d.get("trip") is True

    distance_operated = False
    distance_enabled = _settings_distance_enabled(relay_settings)
    line_diff_operated = False
    unit_diff_operated = False  # bus / transformer / generator zone

    for a in assessments or []:
        d = _row(a)
        el = str(d.get("element") or "").upper().replace(" ", "")
        is_dist = el.startswith("21") or "DISTANCE" in el
        is_line_diff = el.startswith("87L") or (
            "DIFFERENTIAL" in el and "LINE" in el
        )
        is_unit_diff = (
            el.startswith("87B")
            or el.startswith("87T")
            or el.startswith("87G")
            or "BUSZONE" in el
            or ("BUS" in el and "DIFF" in el)
            or ("TRANSFORMER" in el and "DIFF" in el)
        )

        if is_dist:
            if d.get("enabled") is True:
                distance_enabled = True
            if _operated(d):
                distance_operated = True
            continue

        if not _operated(d):
            continue
        if is_line_diff:
            line_diff_operated = True
        elif is_unit_diff:
            unit_diff_operated = True
        elif el.startswith("87") or "DIFFERENTIAL" in el:
            # Ambiguous "87": with line Z1 treat as line-capable; else zone/unit
            if _line_z_usable(line_params):
                line_diff_operated = True
            else:
                unit_diff_operated = True

    if distance_operated:
        return True

    # Primary 87 + backup 21 enabled (may not have operated if 87 cleared first)
    if distance_enabled and (line_diff_operated or unit_diff_operated):
        return True

    # Line differential with line impedance — location is an engineering input
    if line_diff_operated and _line_z_usable(line_params):
        return True

    # Pure bus/xfmr/gen differential, or OC/EF-only: no km
    return False


def classify_fault(
    elec: ElectricalAnalysisResult,
    *,
    line_params: Optional[dict[str, Any]] = None,
    ct_vt_ratios: Optional[dict[str, Any]] = None,
    relay_settings: Optional[dict[str, Any]] = None,
    assessments: Optional[list[Any]] = None,
    distance_applicable: Optional[bool] = None,
    elec_remote: Optional[ElectricalAnalysisResult] = None,
    sync_offset_us: Optional[float] = None,
) -> FaultClassificationResult:
    from fault_analysis.location import compute_fault_locations, normalize_line_params

    feat = _features_from_electrical(elec)
    ft, status, conf = _classify_from_features(feat)
    limitations: list[str] = []
    if not feat.get("available"):
        limitations.append("Three-phase current evidence NOT AVAILABLE")

    if distance_applicable is None:
        distance_applicable = distance_scheme_applicable(
            assessments=assessments,
            line_params=line_params,
            relay_settings=relay_settings,
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
            elec_remote=elec_remote,
            sync_offset_us=sync_offset_us,
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
