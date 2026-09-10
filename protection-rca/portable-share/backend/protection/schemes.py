"""Protection scheme library — composition profiles over ANSI elements.

Industry practice: RCA / distance applicability follow the *scheme* (87L+21,
POTT, bus unit, BF cascade), not a single ANSI code in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from common.rules_path import load_yaml, resolve_rules_root


@dataclass
class SchemeProfile:
    id: str
    label: str
    primary_elements: list[str] = field(default_factory=list)
    supporting_elements: list[str] = field(default_factory=list)
    required_digitals: list[str] = field(default_factory=list)  # target roles
    zone: str = "line"  # line | feeder | xfmr | bus | gen | bf | grid
    distance_applicable: bool = False
    evidence_tokens: list[str] = field(default_factory=list)
    rca_hypotheses: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SchemeMatch:
    scheme_id: str
    label: str
    score: float
    zone: str
    distance_applicable: bool
    evidence_tokens: list[str] = field(default_factory=list)
    matched_elements: list[str] = field(default_factory=list)
    matched_digitals: list[str] = field(default_factory=list)
    missing_digitals: list[str] = field(default_factory=list)
    rca_hypotheses: list[str] = field(default_factory=list)
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _schemes_dir() -> Path:
    return resolve_rules_root() / "schemes"


def load_scheme_profiles() -> list[SchemeProfile]:
    root = _schemes_dir()
    profiles: list[SchemeProfile] = []
    if not root.is_dir():
        return profiles
    for path in sorted(root.glob("*.yaml")):
        data = load_yaml(path)
        if not isinstance(data, dict):
            continue
        sid = str(data.get("id") or path.stem).strip()
        if not sid:
            continue
        profiles.append(
            SchemeProfile(
                id=sid,
                label=str(data.get("label") or sid),
                primary_elements=[str(x).upper() for x in (data.get("primary_elements") or [])],
                supporting_elements=[
                    str(x).upper() for x in (data.get("supporting_elements") or [])
                ],
                required_digitals=[
                    str(x).upper() for x in (data.get("required_digitals") or [])
                ],
                zone=str(data.get("zone") or "line").lower(),
                distance_applicable=bool(data.get("distance_applicable", False)),
                evidence_tokens=[str(x) for x in (data.get("evidence_tokens") or [])],
                rca_hypotheses=[str(x) for x in (data.get("rca_hypotheses") or [])],
                description=str(data.get("description") or ""),
            )
        )
    return profiles


def detect_schemes(
    *,
    operated_elements: list[str] | set[str],
    enabled_elements: Optional[list[str] | set[str]] = None,
    digital_roles: Optional[list[str] | set[str]] = None,
    profiles: Optional[list[SchemeProfile]] = None,
) -> list[SchemeMatch]:
    """Rank scheme compositions from operated / enabled ANSI codes + digital roles."""
    operated = {str(x).upper().strip() for x in operated_elements if x}
    enabled = {str(x).upper().strip() for x in (enabled_elements or []) if x}
    roles = {str(x).upper().strip() for x in (digital_roles or []) if x}
    present = operated | enabled
    profiles = profiles if profiles is not None else load_scheme_profiles()
    matches: list[SchemeMatch] = []

    for p in profiles:
        if not p.primary_elements:
            continue
        prim_hit = [e for e in p.primary_elements if e in present]
        if not prim_hit:
            continue
        # Prefer operated primary
        prim_op = [e for e in p.primary_elements if e in operated]
        if not prim_op and not any(e in enabled for e in p.primary_elements):
            continue
        supp_hit = [e for e in p.supporting_elements if e in present]
        dig_hit = [r for r in p.required_digitals if r in roles]
        dig_miss = [r for r in p.required_digitals if r not in roles]

        score = 0.0
        score += 0.55 * (len(prim_op) / max(len(p.primary_elements), 1))
        score += 0.20 * (len(prim_hit) / max(len(p.primary_elements), 1))
        if p.supporting_elements:
            score += 0.15 * (len(supp_hit) / len(p.supporting_elements))
        else:
            score += 0.05
        if p.required_digitals:
            score += 0.15 * (len(dig_hit) / len(p.required_digitals))
            if dig_miss and "COMM" in p.required_digitals and "COMM" not in roles:
                score -= 0.05
        else:
            score += 0.05
        # Boost when primary actually operated
        if prim_op:
            score += 0.08
        score = max(0.0, min(1.0, score))
        if score < 0.35:
            continue

        tokens = list(p.evidence_tokens)
        tokens.append(f"scheme_profile_{p.id}")
        if dig_hit:
            tokens.append("scheme_digitals_matched")
        if dig_miss and p.required_digitals:
            tokens.append("scheme_digitals_incomplete")

        matches.append(
            SchemeMatch(
                scheme_id=p.id,
                label=p.label,
                score=round(score, 4),
                zone=p.zone,
                distance_applicable=p.distance_applicable,
                evidence_tokens=tokens,
                matched_elements=sorted(set(prim_hit + supp_hit)),
                matched_digitals=dig_hit,
                missing_digitals=dig_miss,
                rca_hypotheses=list(p.rca_hypotheses),
                description=p.description,
            )
        )

    matches.sort(key=lambda m: (-m.score, m.scheme_id))
    return matches


def primary_scheme(matches: list[SchemeMatch]) -> Optional[SchemeMatch]:
    return matches[0] if matches else None


def scheme_tokens(matches: list[SchemeMatch], *, top_n: int = 3) -> set[str]:
    bag: set[str] = set()
    for m in matches[:top_n]:
        bag.update(m.evidence_tokens)
        if m.distance_applicable:
            bag.add("scheme_distance_profile")
        bag.add(f"scheme_zone_{m.zone}")
    if matches:
        bag.add("scheme_library_matched")
        top = matches[0]
        bag.add(f"scheme_id_{top.scheme_id}")
    return bag
