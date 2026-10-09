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
    event_class: Optional[str] = None
    event_class_status: Optional[str] = None

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

    # Prefer prefault baseline when available (fault-window vs early-cycle RMS).
    # Else relative participation: elevated if ≥ 70% of peak phase current.
    det = {}
    if isinstance(getattr(elec, "detectors", None), dict):
        det = elec.detectors or {}
    pre = det.get("prefault_rms") if isinstance(det.get("prefault_rms"), dict) else {}
    use_prefault = bool(
        pre.get("IA") is not None and pre.get("IB") is not None and pre.get("IC") is not None
    )
    thr = 0.7 * peak

    def elevated(x: Optional[float], role: str) -> Optional[bool]:
        if x is None:
            return None
        if use_prefault:
            try:
                base = float(pre.get(role) or 0.0)
            except (TypeError, ValueError):
                base = 0.0
            # Faulted phase: clearly above load; healthy phases stay near prefault
            if base > 1e-6:
                return bool(x >= max(1.5 * base, 0.25 * peak))
            return bool(x >= thr)
        return bool(x >= thr)

    ground = False
    if i0 is not None and peak > 0:
        ground = bool(i0 >= 0.15 * peak)

    return {
        "available": True,
        "Ia": ia,
        "Ib": ib,
        "Ic": ic,
        "Ia_elevated": elevated(ia, "IA"),
        "Ib_elevated": elevated(ib, "IB"),
        "Ic_elevated": elevated(ic, "IC"),
        "I0": i0,
        "I2": i2,
        "ground": ground,
        "threshold": thr,
        "elevation_method": "prefault_ratio" if use_prefault else "peak_relative",
        "prefault_rms": dict(pre) if use_prefault else None,
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


def _asserted_digital_names(timeline: Optional[list[Any]] = None) -> list[str]:
    """Collect asserted DR digital / SOE / event-report labels for phase typing."""
    names: list[str] = []
    for ev in timeline or []:
        src = getattr(ev, "source", None)
        if src is None and isinstance(ev, dict):
            src = ev.get("source")
        src = str(src or "")
        md = getattr(ev, "metadata", None)
        if md is None and isinstance(ev, dict):
            md = ev.get("metadata")
        if not isinstance(md, dict):
            md = {}
        if src.startswith("digital:"):
            names.append(src.split(":", 1)[1])
        elif src.startswith("SOE:"):
            names.append(src.split(":", 1)[1])
            for k in ("signal", "point_tag", "label"):
                if md.get(k):
                    names.append(str(md[k]))
        elif src.startswith("RELAY_EVENT_REPORT:"):
            if md.get("label"):
                names.append(str(md["label"]))
            elif md.get("signal"):
                names.append(str(md["signal"]))
        et = getattr(ev, "event_type", None) or (
            ev.get("event_type") if isinstance(ev, dict) else ""
        )
        if str(et) in (
            "protection_trip",
            "protection_pickup",
            "breaker_trip_command",
            "fault_inception",
        ):
            # labels already captured above when source-prefixed
            pass
    return names


def _phases_from_names(names: list[str]) -> set[str]:
    """Parse A/B/C involvement from digital / SOE / event-report channel text.

    Indian RYB: ``R PH``→A, ``Y PH``→B, ``B PH`` (blue)→C.
    Western ABC: ``Ph A`` / ``Trip A`` / ``50A`` / ``A-G`` / ``IA>``.
    Note: bare ``B PH`` is Blue (→C), not Western phase B — use ``PH B`` / ``TRIP B``.
    """
    import re

    phases: set[str] = set()
    for raw in names:
        n = (raw or "").upper().replace("_", " ")
        if not n.strip():
            continue

        # Explicit multi-phase fault tokens
        if re.search(r"\b(?:ABCG|ABC|3[\s\-]?PH(?:ASE)?|THREE[\s\-]?PHASE)\b", n):
            phases.update({"A", "B", "C"})
            continue
        if re.search(r"\bABG\b|\bA[\-/]B\b|\bAB\s*(?:FAULT|TRIP)", n):
            phases.update({"A", "B"})
        if re.search(r"\bBCG\b|\bB[\-/]C\b|\bBC\s*(?:FAULT|TRIP)", n):
            phases.update({"B", "C"})
        if re.search(r"\bCAG\b|\bC[\-/]A\b|\bCA\s*(?:FAULT|TRIP)", n):
            phases.update({"C", "A"})

        # Indian RYB + shared "x PH TRIP" (A PH / R PH → A; B PH → Blue/C; C PH → C)
        if re.search(r"\b(?:R|A)\s*PH(?:ASE)?\s*(?:TRIP|START|OPTD|FAULT|PU|PICK)?\b", n):
            phases.add("A")
        if re.search(r"\bY\s*PH(?:ASE)?\s*(?:TRIP|START|OPTD|FAULT|PU|PICK)?\b", n):
            phases.add("B")
        if re.search(r"\bB\s*PH(?:ASE)?\s*(?:TRIP|START|OPTD|FAULT|PU|PICK)?\b", n):
            phases.add("C")  # Blue in RYB
        if re.search(r"\bC\s*PH(?:ASE)?\s*(?:TRIP|START|OPTD|FAULT|PU|PICK)?\b", n):
            phases.add("C")

        # Western / IEC (PH B / TRIP B / 50B) — not "B PH" (handled as Blue above)
        for letter, token in (("A", "A"), ("B", "B"), ("C", "C")):
            if re.search(rf"\bPH(?:ASE)?\s+{token}\b", n):
                phases.add(letter)
            if re.search(rf"\bTRIP\s+(?:ON\s+)?(?:PHASE\s+)?{token}\b", n):
                phases.add(letter)
            if re.search(rf"\b{token}\s+TRIP\b", n):
                phases.add(letter)
            if re.search(rf"\bPH{token}\b", n):
                phases.add(letter)
            if re.search(rf"\b(?:50|51|67)[\s/]?{token}\b", n):
                phases.add(letter)
            if re.search(rf"\bI[\s]?{token}\s*[>≥]", n):
                phases.add(letter)
            if re.search(rf"\b{token}[\-/][NG]\b|\b{token}G\b", n):
                phases.add(letter)

    return phases


def _ground_hint_from_names(names: list[str]) -> Optional[bool]:
    """True when digitals/SOE clearly indicate earth/ground involvement."""
    import re

    for raw in names:
        n = (raw or "").upper().replace("_", " ")
        if re.search(
            r"50N|51N|67N|64R|SEF|REF|EARTH|GROUND|RESIDUAL|"
            r"\bI[\s]?N\s*[>≥]|\bI0\b|\bN[\-/]E\b|\bEF\b|"
            r"\b[ABC][\-/][NG]\b|\b[ABC]G\b|\b[RYB][\-/]?E\b|"
            r"\bABG\b|\bBCG\b|\bCAG\b|\bAG\b|\bBG\b|\bCG\b",
            n,
        ):
            return True
    return None


def _fault_type_from_phases(phases: set[str], ground: bool) -> Optional[str]:
    if not phases:
        return None
    if phases == {"A", "B", "C"}:
        return "ABCG" if ground else "ABC"
    if phases == {"A", "B"}:
        return "ABG" if ground else "AB"
    if phases == {"B", "C"}:
        return "BCG" if ground else "BC"
    if phases == {"C", "A"}:
        return "CAG" if ground else "CA"
    if len(phases) == 1:
        return {"A": "AG", "B": "BG", "C": "CG"}[next(iter(phases))]
    return None


def _phase_hint_from_names(names: list[str]) -> Optional[str]:
    """Return A/B/C when digitals show a single-phase trip/start (Indian RYB: R/Y/B)."""
    phases = _phases_from_names(names)
    if len(phases) == 1:
        return next(iter(phases))
    return None


def _refine_with_digital_phase(
    ft: str,
    status: str,
    conf: str,
    feat: dict[str, Any],
    phase_hint: Optional[str],
) -> tuple[str, str, str]:
    """Backward-compatible single-phase refine (tests). Prefer ``_refine_with_digital_phases``."""
    if not phase_hint or phase_hint not in ("A", "B", "C"):
        return ft, status, conf
    return _refine_with_digital_phases(ft, status, conf, feat, {phase_hint})


def _refine_with_digital_phases(
    ft: str,
    status: str,
    conf: str,
    feat: dict[str, Any],
    phases: set[str],
) -> tuple[str, str, str]:
    """Apply digital/SOE phase involvement when electrical typing is weak or over-broad."""
    if not phases:
        return ft, status, conf
    ground = bool(feat.get("ground"))
    mapped = _fault_type_from_phases(phases, ground)
    if not mapped:
        return ft, status, conf

    apply = False
    if ft in ("UNKNOWN",) or status in ("INCONCLUSIVE", "UNKNOWN"):
        apply = True
    elif ft in ("ABC", "ABCG") and phases != {"A", "B", "C"}:
        apply = True
    elif ft in ("AB", "ABG", "BC", "BCG", "CA", "CAG") and len(phases) == 1:
        apply = True

    if not apply:
        return ft, status, conf

    if ground or len(phases) >= 2:
        st = ClassificationStatus.CLASSIFIED.value
    else:
        st = ClassificationStatus.PROBABLE.value
    return mapped, st, "MEDIUM"


def motor_start_context(
    digital_names: Optional[list[str]] = None,
    *,
    detectors: Optional[dict[str, Any]] = None,
    assessments: Optional[list[Any]] = None,
) -> dict[str, Any]:
    """Detect motor-protection / starting-current context from DR digitals + ops."""
    import re

    names = [str(n) for n in (digital_names or []) if n]
    name_hit = any(
        re.search(
            r"ANY\s*START|PROLONGED\s*START|STALL|LOCKED?\s*ROTOR|THERMAL|"
            r"START\s*I\s*[>0-9]|START\s*I2|START\s*ISEF|NUMBER\s*OF\s*STARTS|"
            r"INCOMPLETE.?SEQ",
            n,
            re.I,
        )
        for n in names
    )
    det = detectors if isinstance(detectors, dict) else {}
    prefixes = det.get("active_bay_prefixes")
    prefix_hit = False
    if isinstance(prefixes, (list, tuple, set)):
        prefix_hit = any(str(p).upper() == "START" for p in prefixes)

    motor_els = {"46", "48", "49"}
    oc_els = {"50", "51", "50P", "51P", "50N", "51N"}
    pickup_motor = False
    pickup_oc = False
    any_trip = False
    for a in assessments or []:
        d = a.to_dict() if hasattr(a, "to_dict") else (a if isinstance(a, dict) else {})
        code = str(d.get("element") or "").upper().strip()
        act = str(d.get("actual_operation") or "").upper()
        pu = d.get("pickup") is True or act in ("PICKED_UP", "OPERATED", "TRIPPED")
        tr = d.get("trip") is True or act in ("OPERATED", "TRIPPED")
        if tr:
            any_trip = True
        if pu and code in motor_els:
            pickup_motor = True
        if pu and code in oc_els | motor_els:
            pickup_oc = True

    present = bool(name_hit or prefix_hit or pickup_motor)
    # Strong: motor relay context + phase/NPS/OC pickup without trip digital
    likely = bool(present and pickup_oc and not any_trip)
    return {
        "present": present,
        "likely": likely,
        "name_hit": name_hit,
        "prefix_hit": prefix_hit,
        "pickup_motor": pickup_motor,
        "pickup_without_trip": pickup_oc and not any_trip,
    }


def _apply_inrush_and_motor_context(
    ft: str,
    status: str,
    conf: str,
    elec: ElectricalAnalysisResult,
    digital_names: list[str],
    limitations: list[str],
    assessments: Optional[list[Any]] = None,
) -> tuple[str, str, str]:
    """Downgrade false fault framing for energization / motor start signatures."""
    det = getattr(elec, "detectors", None) or {}
    inrush = det.get("magnetizing_inrush") if isinstance(det, dict) else None
    if isinstance(inrush, dict) and str(inrush.get("status") or "").upper() == "POSSIBLE":
        # Do not publish AG/ABG/… as the fault type for magnetizing inrush /
        # transformer charging — phase imbalance is expected during energization.
        limitations.append(
            "Magnetizing inrush / transformer energization POSSIBLE (elevated H2) — "
            "phase fault type suppressed; review 87 restrain / harmonic blocking"
        )
        return (
            FaultType.UNKNOWN.value,
            ClassificationStatus.INCONCLUSIVE.value,
            "LOW",
        )

    motor = motor_start_context(
        digital_names,
        detectors=det if isinstance(det, dict) else {},
        assessments=assessments,
    )
    phaseish = ft in ("ABC", "AB", "BC", "CA", "ABG", "BCG", "CAG", "AG", "BG", "CG")
    if motor.get("likely") and phaseish:
        limitations.append(
            "Motor start / starting-current signature — phase fault type suppressed "
            "(OC/46 pickup without trip on motor-protection DR)"
        )
        return (
            FaultType.UNKNOWN.value,
            ClassificationStatus.INCONCLUSIVE.value,
            "LOW",
        )
    if motor.get("present") and ft in ("ABC", "AB", "BC", "CA") and status == "CLASSIFIED":
        limitations.append(
            "Motor-protection digitals present — phase fault type may reflect start/unbalance"
        )
        return ft, ClassificationStatus.PROBABLE.value, "LOW"
    return ft, status, conf


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
    timeline: Optional[list[Any]] = None,
    digital_channel_names: Optional[list[str]] = None,
) -> FaultClassificationResult:
    from fault_analysis.event_class import EventClass, classify_dfr_event
    from fault_analysis.location import compute_fault_locations, normalize_line_params

    feat = _features_from_electrical(elec)
    limitations: list[str] = []
    if not feat.get("available"):
        limitations.append("Three-phase current evidence NOT AVAILABLE")

    # IEEE/PSRC-style gate: event class BEFORE shunt fault type
    dfr = classify_dfr_event(
        elec,
        timeline=timeline,
        assessments=assessments,
        digital_channel_names=digital_channel_names,
    )
    feat = dict(feat)
    feat["event_classification"] = dfr.to_dict()
    limitations.extend(list(dfr.limitations or []))

    # Asserted digitals + SOE / event-report labels for phase-trip hint
    asserted_names = _asserted_digital_names(timeline)
    earth_element_hit = False
    for a in assessments or []:
        d = a.to_dict() if hasattr(a, "to_dict") else (a if isinstance(a, dict) else {})
        op = str(d.get("actual_operation") or "").upper()
        code = str(d.get("element") or "").upper().replace(" ", "")
        tripped = op in ("OPERATED", "PICKED_UP", "TRIPPED") or d.get("trip") or d.get(
            "pickup"
        )
        if tripped:
            chans: list[str] = []
            for ch in d.get("channel_evidence") or []:
                chans.append(str(ch))
            for eid in d.get("evidence_ids") or []:
                tok = str(eid)
                if tok.upper().startswith("DIGITAL:"):
                    tok = tok.split(":", 1)[1]
                elif tok.upper().startswith("PHYS-"):
                    continue
                chans.append(tok)
            meta = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
            for ch in meta.get("channel_evidence") or meta.get("operate_channels") or []:
                chans.append(str(ch))
            asserted_names.extend(chans)
            if code in (
                "50N",
                "51N",
                "67N",
                "64",
                "64R",
                "SEF",
                "REF",
                "51G",
                "50G",
            ) or code.startswith("50N") or code.startswith("51N"):
                earth_element_hit = True
            # Surface element code text for phase patterns (50A / 51N …)
            if code:
                asserted_names.append(code)

    context_names = list(asserted_names) + list(digital_channel_names or [])
    phases = _phases_from_names(asserted_names)
    ground_digital = _ground_hint_from_names(asserted_names)
    if earth_element_hit or ground_digital is True:
        if feat.get("available"):
            feat["ground"] = True
            feat["ground_from_digital"] = True
        else:
            feat = dict(feat)
            feat["ground"] = True
            feat["ground_from_digital"] = True

    # Explicit non-fault DFR classes suppress AG/AB/… typing.
    # UNKNOWN (no timeline / insufficient V-I-digital gate) still allows
    # current-feature typing so classic AG/ABC fixtures and current-only
    # records remain classifiable — non-fault signatures stay gated above.
    _suppress_shunt = dfr.event_class in (
        EventClass.ENERGIZATION,
        EventClass.MOTOR_START,
        EventClass.SWITCHING,
        EventClass.DISTURBANCE,
    )
    if _suppress_shunt:
        # Inrush / motor / switching / disturbance — not shunt-fault ground
        ft = FaultType.UNKNOWN.value
        status = ClassificationStatus.INCONCLUSIVE.value
        conf = "LOW"
        feat["ground"] = None
        feat["ground_applicable"] = False
        feat["Ia_elevated"] = None
        feat["Ib_elevated"] = None
        feat["Ic_elevated"] = None
        if dfr.reasons:
            limitations.append("DFR reasons: " + "; ".join(dfr.reasons[:4]))
    else:
        ft, status, conf = _classify_from_features(feat)
        if phases:
            feat["digital_phases"] = sorted(phases)
            if len(phases) == 1:
                feat["digital_phase_hint"] = next(iter(phases))
            ft, status, conf = _refine_with_digital_phases(
                ft, status, conf, feat, phases
            )
        # Safety net if class said FAULT/UNKNOWN but inrush/motor still strong
        ft, status, conf = _apply_inrush_and_motor_context(
            ft,
            status,
            conf,
            elec,
            context_names,
            limitations,
            assessments=assessments,
        )
        if dfr.event_class == EventClass.UNKNOWN and ft != FaultType.UNKNOWN.value:
            limitations.append(
                "DFR event class UNKNOWN — shunt type from phase currents / digitals; "
                "confirm with V sag / trip / clearance when available"
            )
        elif (
            ft != FaultType.UNKNOWN.value
            and not feat.get("available")
            and phases
        ):
            limitations.append(
                "Fault type from protection digitals / SOE phase asserts "
                "(three-phase current map not available)"
            )

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
        event_class=dfr.event_class,
        event_class_status=dfr.status,
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
