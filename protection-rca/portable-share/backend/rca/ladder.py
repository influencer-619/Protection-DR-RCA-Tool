"""Excel matrix deep ladder: L1 digital detail, L2 causality, L3 executable fallbacks.

Implements the methodology in ``matrix_v1.yaml``:
  - L1: never invent a missing relay bit — but record every asserted channel
  - L2: reconstruct chronological causality from timestamps
  - L3: waveform-derived evidence may replace a missing dedicated indication
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


# L1 tokens that L3 analogues may substitute (Excel fallback methodology).
# Keys = dedicated relay/SOE bits; values = L3 (or soft) substitutes that count.
L3_FALLBACK_EQUIV: dict[str, tuple[str, ...]] = {
    "earth_fault_element_operated": (
        "earth_fault_l3_inferred",
        "zero_sequence_elevated",
    ),
    "earth_fault_element_picked_up": (
        "earth_fault_l3_inferred",
        "zero_sequence_elevated",
    ),
    "distance_element_operated": (
        "distance_l3_inferred",
        "loop_impedance_available",
        "distance_estimate_available",
    ),
    "differential_operated": (
        "differential_l3_inferred",
    ),
    "transformer_diff_operated": (
        "differential_l3_inferred",
    ),
    "bus_diff_operated": (
        "bus_zone_l3_inferred",
    ),
    "overcurrent_element_operated": (
        "overcurrent_l3_inferred",
        "current_increase_observed",
    ),
    "unbalance_protection_operated": (
        "negative_sequence_elevated",
        "unbalance_l3_inferred",
    ),
    "sotf_element_asserted": (
        "sotf_l3_inferred",
        "switch_onto_fault_context",
    ),
    "bf_logic_satisfied": (
        "bf_l3_inferred",
    ),
    "magnetizing_inrush_possible": (
        "inrush_l3_inferred",
        "harmonic_evidence",
    ),
    "motor_start_possible": (
        "motor_start_l3_inferred",
    ),
}


@dataclass
class DigitalChannelAssert:
    channel: str
    element: Optional[str] = None
    assert_kind: str = "other"  # pickup | trip | intertrip | breaker | reclose | other
    t_s: Optional[float] = None
    source: str = ""
    phase_hint: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LadderDeepResult:
    digital_channels: list[DigitalChannelAssert] = field(default_factory=list)
    l2_causality: dict[str, Any] = field(default_factory=dict)
    l3_fallbacks: list[dict[str, Any]] = field(default_factory=list)
    tokens: set[str] = field(default_factory=set)
    traces: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "digital_channels": [d.to_dict() for d in self.digital_channels[:80]],
            "digital_channel_count": len(self.digital_channels),
            "l2_causality": dict(self.l2_causality),
            "l3_fallbacks": list(self.l3_fallbacks),
            "tokens": sorted(self.tokens),
            "traces": list(self.traces),
        }


def _ev_field(ev: Any, key: str, default: Any = None) -> Any:
    if isinstance(ev, dict):
        return ev.get(key, default)
    return getattr(ev, key, default)


def _ev_meta(ev: Any) -> dict[str, Any]:
    md = _ev_field(ev, "metadata")
    if isinstance(md, dict):
        return md
    return {}


def _classify_assert_kind(name: str, event_type: str = "") -> str:
    n = (name or "").upper()
    et = (event_type or "").lower()
    if "intertrip" in et or re.search(r"INTERTRIP|TRANSFER.?TRIP|\bTT_|\bDTT", n):
        return "intertrip"
    if "reclose" in et or re.search(r"RECLOSE|\b79\b|AUTO.?RECLOSE", n):
        return "reclose"
    if et in ("52a_change", "52b_change") or re.search(r"52A|52B|BREAKER", n):
        return "breaker"
    if "pickup" in et or re.search(r"PICK\s*UP|PICKUP|_PU\b|START", n):
        return "pickup"
    if et in ("protection_trip", "breaker_trip_command") or re.search(
        r"TRIP|OPERATE|_OP\b", n
    ):
        return "trip"
    return "other"


def _phase_from_name(name: str) -> Optional[str]:
    from fault_analysis import _phases_from_names

    ph = _phases_from_names([name])
    if len(ph) == 1:
        return next(iter(ph))
    if ph == {"A", "B", "C"}:
        return "ABC"
    if len(ph) == 2:
        return "".join(sorted(ph))
    return None


def collect_digital_channel_detail(
    *,
    timeline: Optional[list[Any]] = None,
    assessments: Optional[list[Any]] = None,
    digital_channel_names: Optional[list[str]] = None,
) -> tuple[list[DigitalChannelAssert], set[str], list[str]]:
    """Full per-channel digital / SOE / SER assert inventory (L1 detail)."""
    rows: list[DigitalChannelAssert] = []
    seen: set[str] = set()
    tokens: set[str] = set()
    traces: list[str] = []

    def _add(
        channel: str,
        *,
        element: Optional[str] = None,
        assert_kind: str = "other",
        t_s: Optional[float] = None,
        source: str = "",
    ) -> None:
        ch = (channel or "").strip()
        if not ch:
            return
        key = f"{ch}|{assert_kind}|{t_s}"
        if key in seen:
            return
        seen.add(key)
        ph = _phase_from_name(ch)
        rows.append(
            DigitalChannelAssert(
                channel=ch,
                element=element,
                assert_kind=assert_kind,
                t_s=t_s,
                source=source,
                phase_hint=ph,
            )
        )
        if ph:
            tokens.add(f"digital_phase_{ph.lower()}")

    for ev in timeline or []:
        src = str(_ev_field(ev, "source") or "")
        et = str(_ev_field(ev, "event_type") or "")
        md = _ev_meta(ev)
        try:
            t_s = float(_ev_field(ev, "timestamp") or _ev_field(ev, "t_s") or 0.0)
        except (TypeError, ValueError):
            t_s = None
        label = (
            md.get("point_tag")
            or md.get("signal")
            or md.get("channel")
            or md.get("label")
            or (src.split(":", 1)[1] if ":" in src else src)
        )
        el = md.get("element")
        if src.startswith("digital:") or src.startswith("SOE:") or src.startswith(
            "RELAY_EVENT_REPORT:"
        ):
            kind = _classify_assert_kind(str(label), et)
            _add(
                str(label),
                element=str(el) if el else None,
                assert_kind=kind,
                t_s=t_s,
                source=src,
            )
        elif et in (
            "protection_trip",
            "protection_pickup",
            "breaker_trip_command",
            "intertrip",
            "reclose",
            "52a_change",
            "52b_change",
        ):
            kind = _classify_assert_kind(str(label or et), et)
            _add(
                str(label or et),
                element=str(el) if el else None,
                assert_kind=kind,
                t_s=t_s,
                source=src or et,
            )

    for a in assessments or []:
        d = a.to_dict() if hasattr(a, "to_dict") else (a if isinstance(a, dict) else {})
        el = str(d.get("element") or "")
        trip = d.get("trip") is True or str(d.get("actual_operation") or "").upper() in (
            "TRIPPED",
            "OPERATED",
        )
        pickup = d.get("pickup") is True
        evid = list(d.get("evidence_ids") or [])
        meta = d.get("metadata") if isinstance(d.get("metadata"), dict) else {}
        evid.extend(meta.get("channel_evidence") or [])
        timing = d.get("timing") if isinstance(d.get("timing"), dict) else {}
        t_trip = timing.get("trip_time_s")
        t_pu = timing.get("pickup_time_s")
        for eid in evid:
            tok = str(eid)
            if tok.upper().startswith("DIGITAL:"):
                tok = tok.split(":", 1)[1]
            if tok.upper().startswith("PHYS-") or tok.upper().startswith("SER:"):
                if tok.upper().startswith("SER:"):
                    tok = tok.split(":", 1)[1]
                else:
                    continue
            kind = "trip" if trip else ("pickup" if pickup else "other")
            _add(
                tok,
                element=el or None,
                assert_kind=kind,
                t_s=float(t_trip) if t_trip is not None else (
                    float(t_pu) if t_pu is not None else None
                ),
                source=f"assessment:{el}",
            )

    # CFG names present but not necessarily asserted — inventory only
    for n in digital_channel_names or []:
        if n and not any(r.channel == n for r in rows):
            _add(str(n), assert_kind="cfg_present", source="cfg")

    asserted = [r for r in rows if r.assert_kind != "cfg_present"]
    if asserted:
        tokens.add("digital_channel_detail_present")
        trips = sum(1 for r in asserted if r.assert_kind == "trip")
        picks = sum(1 for r in asserted if r.assert_kind == "pickup")
        its = sum(1 for r in asserted if r.assert_kind == "intertrip")
        traces.append(
            f"L1 digital detail: {len(asserted)} asserted channel(s) "
            f"({trips} trip, {picks} pickup, {its} intertrip)"
        )
        # Phase detail from digitals
        phases = {r.phase_hint for r in asserted if r.phase_hint}
        if phases:
            traces.append("L1 phase asserts: " + ", ".join(sorted(phases)))

    return rows, tokens, traces


_CAUSE_ORDER = (
    "fault_inception",
    "protection_pickup",
    "protection_trip",
    "breaker_trip_command",
    "intertrip",
    "current_interruption",
    "52a_change",
    "52b_change",
    "reclose",
)


def score_l2_causality(
    timeline: Optional[list[Any]] = None,
) -> dict[str, Any]:
    """Chronological L2 causality score from SOE / digital / report merge."""
    events: list[tuple[float, str, str]] = []
    for ev in timeline or []:
        et = str(_ev_field(ev, "event_type") or "").lower()
        if et not in _CAUSE_ORDER and et not in (
            "current_increase",
            "fault_inception",
        ):
            continue
        try:
            t = float(_ev_field(ev, "timestamp") or _ev_field(ev, "t_s") or 0.0)
        except (TypeError, ValueError):
            continue
        src = str(_ev_field(ev, "source") or "")
        events.append((t, et, src))
    events.sort(key=lambda x: x[0])

    # Collapse to first occurrence of each role in expected chain
    first: dict[str, float] = {}
    for t, et, _src in events:
        role = et
        if role == "current_increase":
            role = "fault_inception"
        if role in ("52b_change",):
            role = "52a_change"
        if role not in first:
            first[role] = t

    chain = [r for r in _CAUSE_ORDER if r in first]
    order_ok = True
    violations: list[str] = []
    for i in range(len(chain) - 1):
        a, b = chain[i], chain[i + 1]
        if first[a] > first[b] + 1e-9:
            # Allow intertrip slightly before local trip on backup end
            if {a, b} == {"protection_trip", "intertrip"}:
                continue
            if {a, b} == {"breaker_trip_command", "intertrip"}:
                continue
            order_ok = False
            violations.append(f"{a}@{first[a]:.4f}s after {b}@{first[b]:.4f}s")

    # Score: length of meaningful chain + order
    roles_hit = len(chain)
    score = min(1.0, 0.15 * roles_hit)
    if roles_hit >= 3 and order_ok:
        score = min(1.0, score + 0.35)
    elif roles_hit >= 2 and order_ok:
        score = min(1.0, score + 0.20)
    if not order_ok:
        score = max(0.0, score - 0.25)

    tokens: set[str] = set()
    traces: list[str] = []
    if roles_hit >= 2:
        tokens.add("l2_sequence_present")
    if roles_hit >= 3 and order_ok:
        tokens.add("l2_causality_ok")
        traces.append(
            "L2 causality OK: " + " → ".join(f"{r}@{first[r]*1000:.0f}ms" for r in chain[:6])
        )
    elif roles_hit >= 2:
        tokens.add("l2_causality_weak")
        traces.append(
            "L2 causality weak: "
            + " → ".join(chain[:6])
            + (f" ({'; '.join(violations[:2])})" if violations else "")
        )
    if "fault_inception" in first and (
        "protection_trip" in first or "breaker_trip_command" in first
    ):
        tokens.add("l2_inception_before_trip")
    if "intertrip" in first and (
        "protection_trip" in first or "current_interruption" in first
    ):
        tokens.add("l2_intertrip_in_sequence")
    if "reclose" in first and "protection_trip" in first:
        if first["reclose"] >= first.get("protection_trip", first["reclose"]):
            tokens.add("l2_reclose_after_trip")

    return {
        "order_ok": order_ok if roles_hit >= 2 else None,
        "score": round(score, 3),
        "chain": chain,
        "first_times_s": {k: round(v, 6) for k, v in first.items()},
        "violations": violations,
        "tokens": sorted(tokens),
        "traces": traces,
    }


def apply_l3_fallbacks(
    bag: set[str],
    *,
    electrical_flags: Optional[dict[str, Any]] = None,
    fault: Any = None,
) -> tuple[set[str], list[dict[str, Any]], list[str]]:
    """Executable L3 substitutes when dedicated L1 bits are missing.

    Adds inferred tokens (never invents COMTRADE channels). Matrix matching
    treats these as equivalent to the missing L1 bit via ``L3_FALLBACK_EQUIV``.
    """
    flags = electrical_flags or {}
    feat: dict[str, Any] = {}
    if fault is not None:
        feat = getattr(fault, "evidence", None) or {}
        if not isinstance(feat, dict):
            feat = {}
    ft = str(getattr(fault, "fault_type", None) or flags.get("fault_type") or "")
    status = str(getattr(fault, "status", None) or "")
    added: set[str] = set()
    applied: list[dict[str, Any]] = []
    traces: list[str] = []

    def _num(*keys: str) -> Optional[float]:
        for k in keys:
            v = flags.get(k)
            if v is None:
                v = feat.get(k)
            try:
                if v is not None:
                    return float(v)
            except (TypeError, ValueError):
                continue
        return None

    i_max = _num("I_max_a", "I_fault_a") or 0.0
    i0 = _num("I0", "I0_a")
    i2 = _num("I2", "I2_a")
    ground = bool(feat.get("ground") or flags.get("ground_involved") or "ground_involved" in bag)
    typed = status in ("CLASSIFIED", "PROBABLE") and ft not in ("", "UNKNOWN")

    # Earth / REF bit missing → residual / I0 / AG-BG-CG
    if "earth_fault_element_operated" not in bag and "earth_fault_l3_inferred" not in bag:
        if (
            (i0 is not None and i_max > 0 and i0 >= 0.15 * i_max)
            or ground
            or ft in ("AG", "BG", "CG", "ABG", "BCG", "CAG", "ABCG")
        ) and (typed or "current_increase_observed" in bag or "fault_classified" in bag):
            added.add("earth_fault_l3_inferred")
            added.add("zero_sequence_elevated")
            applied.append(
                {
                    "missing_l1": "earth_fault_element_operated",
                    "inferred": "earth_fault_l3_inferred",
                    "basis": "I0/residual or ground fault type from DR",
                }
            )

    # Distance bit missing → Z1 / loop impedance available
    if "distance_element_operated" not in bag and "distance_l3_inferred" not in bag:
        if "loop_impedance_available" in bag or "distance_estimate_available" in bag:
            added.add("distance_l3_inferred")
            applied.append(
                {
                    "missing_l1": "distance_element_operated",
                    "inferred": "distance_l3_inferred",
                    "basis": "impedance / distance estimate from DR phasors",
                }
            )

    # OC bit missing → strong current rise + trip command / interruption
    if "overcurrent_element_operated" not in bag and "overcurrent_l3_inferred" not in bag:
        if "current_increase_observed" in bag and (
            "trip_observed" in bag
            or "trip_command_observed" in bag
            or "successful_clearing" in bag
        ):
            # Only if no differential already explains the trip
            if "differential_operated" not in bag:
                added.add("overcurrent_l3_inferred")
                applied.append(
                    {
                        "missing_l1": "overcurrent_element_operated",
                        "inferred": "overcurrent_l3_inferred",
                        "basis": "fault current increase + trip/clearance on DR",
                    }
                )

    # NPS / 46 bit missing → I2 elevated
    if (
        "unbalance_protection_operated" not in bag
        and "unbalance_l3_inferred" not in bag
        and "negative_sequence_elevated" in bag
    ):
        added.add("unbalance_l3_inferred")
        applied.append(
            {
                "missing_l1": "unbalance_protection_operated",
                "inferred": "unbalance_l3_inferred",
                "basis": "I2 elevated from three-phase currents",
            }
        )

    # Inrush bit missing → H2 / energization class
    if "magnetizing_inrush_possible" not in bag and "inrush_l3_inferred" not in bag:
        if "harmonic_evidence" in bag or "dfr_non_fault_event" in bag:
            ec = str(flags.get("event_class") or "")
            if ec == "ENERGIZATION" or "electrical_no_fault" in bag:
                added.add("inrush_l3_inferred")
                added.add("magnetizing_inrush_possible")
                applied.append(
                    {
                        "missing_l1": "inrush_element",
                        "inferred": "inrush_l3_inferred",
                        "basis": "H2 / energization waveform signature",
                    }
                )

    # SOTF bit missing → close + immediate fault
    if "sotf_element_asserted" not in bag and "sotf_l3_inferred" not in bag:
        if "breaker_close_observed" in bag and "fault_classified" in bag:
            added.add("sotf_l3_inferred")
            added.add("switch_onto_fault_context")
            applied.append(
                {
                    "missing_l1": "sotf_element_asserted",
                    "inferred": "sotf_l3_inferred",
                    "basis": "CB close timing + immediate fault signature",
                }
            )

    # BF logic missing → persist + trip without interrupt
    if "bf_logic_satisfied" not in bag and "bf_l3_inferred" not in bag:
        if "current_persists" in bag and (
            "trip_command_observed" in bag or "bf_element_operated" in bag
        ):
            added.add("bf_l3_inferred")
            applied.append(
                {
                    "missing_l1": "bf_logic_satisfied",
                    "inferred": "bf_l3_inferred",
                    "basis": "trip command with current persistence on DR",
                }
            )

    if applied:
        added.add("l3_fallback_applied")
        traces.append(
            "L3 fallback applied for missing L1: "
            + ", ".join(a["missing_l1"] for a in applied)
        )

    return added, applied, traces


def build_ladder_deep(
    *,
    bag: set[str],
    timeline: Optional[list[Any]] = None,
    assessments: Optional[list[Any]] = None,
    digital_channel_names: Optional[list[str]] = None,
    electrical_flags: Optional[dict[str, Any]] = None,
    fault: Any = None,
) -> LadderDeepResult:
    """Run L1 digital detail + L2 causality + L3 fallbacks; merge tokens."""
    out = LadderDeepResult()
    digs, dig_toks, dig_tr = collect_digital_channel_detail(
        timeline=timeline,
        assessments=assessments,
        digital_channel_names=digital_channel_names,
    )
    out.digital_channels = digs
    out.tokens |= dig_toks
    out.traces.extend(dig_tr)

    caus = score_l2_causality(timeline)
    out.l2_causality = {k: v for k, v in caus.items() if k != "tokens"}
    out.tokens |= set(caus.get("tokens") or [])
    out.traces.extend(list(caus.get("traces") or []))

    # Merge causality tokens into working bag for fallback decisions
    work = set(bag) | out.tokens
    fb_toks, fb_applied, fb_tr = apply_l3_fallbacks(
        work, electrical_flags=electrical_flags, fault=fault
    )
    out.tokens |= fb_toks
    out.l3_fallbacks = fb_applied
    out.traces.extend(fb_tr)
    return out


def token_satisfied(bag: set[str], token: str) -> bool:
    """True if token is present or an L3 fallback equivalent is present."""
    if token in bag:
        return True
    for alt in L3_FALLBACK_EQUIV.get(token, ()):
        if alt in bag:
            return True
    return False
