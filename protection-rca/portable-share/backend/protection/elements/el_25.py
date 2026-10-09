"""Protection element 25 — Synchronism check (ΔV / Δf / Δφ)."""

from __future__ import annotations

import re
from typing import Any, Optional

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess
from protection.physics import _c, sync_check_25

# Channel-name hints for bus vs line / sync voltages (not phase VA vs VB).
_BUS_NAME = re.compile(
    r"V?BUS|BUS.?V|V.?BUS|ULOCAL|V.?LOCAL|VSYN.?BUS|SYNC.?BUS|CHECK.?SYNC.?BUS",
    re.I,
)
_LINE_NAME = re.compile(
    r"V?LINE|LINE.?V|V.?LINE|UREMOTE|V.?REMOTE|VSYN.?LINE|SYNC.?LINE|"
    r"DEAD.?LINE|CHECK.?SYNC.?LINE|VSYNCH?(?!.*BUS)",
    re.I,
)


def _extract_phasor(raw: Any) -> Optional[complex]:
    """Unwrap SignalResult-like dicts then parse magnitude/angle or real/imag."""
    if raw is None:
        return None
    p = _c(raw)
    if p is not None:
        return p
    if isinstance(raw, dict):
        if "value" in raw:
            return _extract_phasor(raw.get("value"))
        # Nested physics payload
        for k in ("phasor", "complex", "vector"):
            if k in raw:
                p = _extract_phasor(raw.get(k))
                if p is not None:
                    return p
    return None


def _phasor_from_keys(elec: dict[str, Any], *keys: str) -> Optional[complex]:
    for k in keys:
        p = _extract_phasor(elec.get(k))
        if p is not None:
            return p
    ph = elec.get("phasors")
    if not isinstance(ph, dict):
        return None
    roles = elec.get("channel_roles") or {}
    inv = {str(v).upper(): k for k, v in roles.items()} if isinstance(roles, dict) else {}
    for role in keys:
        candidates = [role, role.upper() if isinstance(role, str) else None]
        if isinstance(role, str) and role.isupper():
            candidates.append(inv.get(role))
        for candidate in candidates:
            if not candidate:
                continue
            p = _extract_phasor(ph.get(candidate))
            if p is not None:
                return p
    return None


def _phasors_by_channel_hint(elec: dict[str, Any]) -> tuple[Optional[complex], Optional[complex]]:
    """Resolve bus/line from COMTRADE channel names (dual VT sync-check)."""
    ph = elec.get("phasors")
    if not isinstance(ph, dict) or not ph:
        return None, None
    bus: Optional[complex] = None
    line: Optional[complex] = None
    bus_name = line_name = None
    for name, raw in ph.items():
        n = str(name)
        p = _extract_phasor(raw)
        if p is None:
            continue
        if bus is None and _BUS_NAME.search(n.replace(" ", "").replace("_", "").replace("-", "")):
            # Prefer phase-A when multiple bus channels
            if bus_name is None or re.search(r"A\b|L1|PHA", n, re.I):
                bus, bus_name = p, n
        if line is None and _LINE_NAME.search(n.replace(" ", "").replace("_", "").replace("-", "")):
            if line_name is None or re.search(r"A\b|L1|PHA", n, re.I):
                line, line_name = p, n
    return bus, line


def _dual_end_from_multi(elec: dict[str, Any]) -> tuple[Optional[complex], Optional[complex]]:
    """Local/remote or multi_end stamps from combined / peer analysis."""
    multi = elec.get("multi_end") if isinstance(elec.get("multi_end"), dict) else {}
    v_bus = _extract_phasor(
        elec.get("v_bus")
        or elec.get("V_bus")
        or elec.get("v_local")
        or multi.get("v_bus")
        or multi.get("v_local")
    )
    v_line = _extract_phasor(
        elec.get("v_line")
        or elec.get("V_line")
        or elec.get("v_remote")
        or multi.get("v_line")
        or multi.get("v_remote")
    )
    return v_bus, v_line


class Element_25(ProtectionElement):
    element_code = "25"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        result = base_assess("25", ctx, electrical_fault_hint=False)
        result.metadata["description"] = "Synchronism check"

        elec = ctx.electrical
        v_bus, v_line = _dual_end_from_multi(elec)
        if v_bus is None or v_line is None:
            hb, hl = _phasors_by_channel_hint(elec)
            v_bus = v_bus if v_bus is not None else hb
            v_line = v_line if v_line is not None else hl
        # Explicit role keys only — never VA vs VB (those are phases, not sync sources)
        if v_bus is None:
            v_bus = _phasor_from_keys(
                elec, "v_bus", "V_bus", "v_local", "V_local", "VA_LOCAL", "V_LOCAL", "VBUS"
            )
        if v_line is None:
            v_line = _phasor_from_keys(
                elec,
                "v_line",
                "V_line",
                "v_remote",
                "V_remote",
                "VA_REMOTE",
                "V_REMOTE",
                "VLINE",
                "V_line_a",
            )

        try:
            dv = float(ctx.settings.get("dv_max_pu") or 0.05)
        except (TypeError, ValueError):
            dv = 0.05
        try:
            df = float(ctx.settings.get("df_max_hz") or 0.2)
        except (TypeError, ValueError):
            df = 0.2
        try:
            dphi = float(ctx.settings.get("dphi_max_deg") or 20.0)
        except (TypeError, ValueError):
            dphi = 20.0

        f_bus = elec.get("f_bus_hz") or elec.get("frequency_hz")
        f_line = elec.get("f_line_hz") or elec.get("frequency_remote_hz")

        phys = sync_check_25(
            v_bus=v_bus,
            v_line=v_line,
            f_bus_hz=f_bus,
            f_line_hz=f_line,
            dv_max_pu=dv,
            df_max_hz=df,
            dphi_max_deg=dphi,
        )
        result.metadata["physics"] = phys
        if phys.get("status") == "OK":
            if phys.get("permit_close") is True and result.enabled is not False:
                result.expected_operation = "OPERATE"
            elif phys.get("permit_close") is False:
                result.expected_operation = "NOT_OPERATE"
            result.evidence_ids = list(result.evidence_ids) + ["PHYS-25-SYNC"]
            timing = dict(result.timing or {})
            timing["sync"] = {
                "dv_pu": phys.get("dv_pu"),
                "df_hz": phys.get("df_hz"),
                "dphi_deg": phys.get("dphi_deg"),
                "permit_close": phys.get("permit_close"),
            }
            result.timing = timing
        else:
            if result.expected_operation == "OPERATE" and ctx.observations.trip is not True:
                result.expected_operation = "UNKNOWN"
        return result


ELEMENT = Element_25()
