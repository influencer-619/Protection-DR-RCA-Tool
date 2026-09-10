"""Fault-aware severity scoring for consistency findings.

Inspired by NERC MIDAS misoperation impact scoring (voltage/equipment/cause/category
factors), adapted to inputs available in this platform:

  severity ≈ f(finding outcome, fault type/status, protected-zone element)

Rules of thumb (engineering practice):
  - Inconsistency during a multi-phase / bus-xfmr-gen zone fault ranks higher
  - UNVERIFIABLE data gaps stay at most MEDIUM unless the check is critical
  - CONSISTENT findings stay INFO/LOW — fault does not inflate them
  - Never invent fault severity without classified/probable fault evidence
"""

from __future__ import annotations

from typing import Any, Optional

from app.core.enums import Severity

_ORDER = [
    Severity.INFO.value,
    Severity.LOW.value,
    Severity.MEDIUM.value,
    Severity.HIGH.value,
    Severity.CRITICAL.value,
]

# Fault-type impact (0–3), analogous to MIDAS “during fault” weight
_FAULT_IMPACT: dict[str, int] = {
    "AG": 1,
    "BG": 1,
    "CG": 1,
    "AB": 2,
    "BC": 2,
    "CA": 2,
    "ABG": 2,
    "BCG": 2,
    "CAG": 2,
    "ABC": 3,
    "ABCG": 3,
}

# Protected-zone / scheme weight (0–3)
_ZONE_IMPACT: dict[str, int] = {
    "87B": 3,
    "87T": 3,
    "87G": 3,
    "87RGF": 3,
    "87L": 2,
    "21": 2,
    "21G": 2,
    "21P": 2,
    "50BF": 3,
    "86": 3,
    "50": 1,
    "51": 1,
    "50P": 1,
    "51P": 1,
    "50N": 1,
    "51N": 1,
    "67": 1,
    "67N": 1,
    "67P": 1,
    "27": 1,
    "59": 1,
    "81U": 1,
    "81O": 1,
    "81R": 1,
    "79": 1,
    "25": 0,
    "68": 1,
    "78": 2,
    "32R": 1,
    "46": 1,
}


def _idx(sev: str) -> int:
    s = (sev or Severity.MEDIUM.value).upper()
    try:
        return _ORDER.index(s)
    except ValueError:
        return _ORDER.index(Severity.MEDIUM.value)


def _clamp(i: int) -> str:
    return _ORDER[max(0, min(len(_ORDER) - 1, i))]


def fault_impact(fault_type: Optional[str], fault_status: Optional[str]) -> int:
    st = (fault_status or "").upper()
    if st not in ("CLASSIFIED", "PROBABLE"):
        return 0
    return _FAULT_IMPACT.get((fault_type or "").upper(), 0)


def zone_impact(element: Optional[str], check_type: Optional[str] = None) -> int:
    el = (element or "").upper().strip()
    if el in _ZONE_IMPACT:
        return _ZONE_IMPACT[el]
    # Family checks may use multi-element labels
    ct = (check_type or "").lower()
    if ct in ("differential", "breaker_failure", "lockout"):
        return 3
    if ct in ("distance", "out_of_step"):
        return 2
    if ct in ("overcurrent", "earth_fault", "directional", "voltage", "frequency"):
        return 1
    return 1


def adjust_finding_severity(
    base_severity: str,
    *,
    status: str,
    element: str = "",
    check_type: str = "",
    fault_type: Optional[str] = None,
    fault_status: Optional[str] = None,
) -> str:
    """Adjust a finding's base severity using fault + zone context."""
    base = (base_severity or Severity.MEDIUM.value).upper()
    st = (status or "").upper()

    # Consistent / info outcomes: do not escalate with fault
    if st == "CONSISTENT":
        return Severity.INFO.value if base in (Severity.INFO.value, Severity.LOW.value) else base

    fi = fault_impact(fault_type, fault_status)
    zi = zone_impact(element, check_type)
    i = _idx(base)

    if st == "INCONSISTENT":
        # During multi-phase / unit-protection zone → escalate
        bump = 0
        if fi >= 3:
            bump += 1
        elif fi >= 2:
            bump += 1 if zi >= 2 else 0
        if zi >= 3 and fi >= 1:
            bump = max(bump, 1)
        # Critical setting contradictions already CRITICAL/HIGH — keep floor
        if "enabled_vs_trip" in (check_type or "") and "FALSE" in (element or ""):
            pass
        return _clamp(i + bump)

    if st == "UNVERIFIABLE":
        # Incomplete data: never escalate above MEDIUM from fault alone
        if zi >= 3:
            return Severity.MEDIUM.value
        if fi >= 2:
            return Severity.MEDIUM.value
        return _clamp(min(i, _idx(Severity.MEDIUM.value)))

    if st == "DATA_QUALITY_ISSUE":
        return _clamp(max(i, _idx(Severity.MEDIUM.value)) + (1 if fi >= 3 else 0))

    return base


def event_severity_summary(
    *,
    finding_severities: list[str],
    fault_type: Optional[str] = None,
    fault_status: Optional[str] = None,
) -> str:
    """Event-level severity: max finding severity, with fault floor when classified."""
    ranks = [_idx(s) for s in finding_severities] if finding_severities else []
    top = max(ranks) if ranks else _idx(Severity.INFO.value)
    fi = fault_impact(fault_type, fault_status)
    # Classified multi-phase fault alone warrants at least MEDIUM attention
    if fi >= 3:
        top = max(top, _idx(Severity.HIGH.value))
    elif fi >= 2:
        top = max(top, _idx(Severity.MEDIUM.value))
    elif fi >= 1:
        top = max(top, _idx(Severity.MEDIUM.value))
    return _clamp(top)


def severity_rationale(
    *,
    base: str,
    adjusted: str,
    status: str,
    element: str,
    fault_type: Optional[str],
    fault_status: Optional[str],
) -> str:
    if base == adjusted:
        return f"Severity {adjusted} from check outcome ({status})"
    return (
        f"Severity {base}→{adjusted} using fault context "
        f"{fault_type or 'UNKNOWN'}/{fault_status or 'UNKNOWN'} "
        f"and element {element or '—'}"
    )
