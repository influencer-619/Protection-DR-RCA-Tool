"""Modular protection rule engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from common.rules_path import load_yaml, resolve_rules_root
from event_reconstruction.timeline import TimelineEvent
from protection.elements.base_dispatch import get_element
from protection.models import (
    ElementContext,
    ElementObservation,
    ProtectionAssessment,
)
from settings.hierarchy.resolver import SettingRecord, SettingResolution, resolve_setting


@dataclass
class ProtectionEngineResult:
    assessments: list[ProtectionAssessment] = field(default_factory=list)
    rules_version: str = "1.0.0"
    limitations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessments": [a.to_dict() for a in self.assessments],
            "rules_version": self.rules_version,
            "limitations": self.limitations,
        }


def _load_rule_configs() -> dict[str, dict[str, Any]]:
    root = resolve_rules_root() / "protection"
    configs: dict[str, dict[str, Any]] = {}
    if not root.is_dir():
        return configs
    for path in sorted(root.glob("*.yaml")):
        data = load_yaml(path)
        if isinstance(data, dict) and "element" in data:
            configs[str(data["element"])] = data
    return configs


def _match_element_from_channel(name: str) -> Optional[str]:
    n = name.upper()
    # Prefer longer / more specific codes first (ANSI suffixes)
    for code in (
        "87RGF",
        "50BF",
        "50NBF",
        "87GT",
        "87G",
        "87T",
        "87L",
        "87B",
        "51N",
        "50N",
        "67N",
        "67P",
        "50P",
        "51P",
        "21G",
        "21P",
        "32R",
        "81U",
        "81O",
        "81R",
        "32",
        "46",
        "68",
        "78",
        "21",
        "50",
        "51",
        "67",
        "27",
        "59",
        "79",
        "86",
        "25",
        "87",  # bare 87_TRIP / 87_PICKUP (family not specified)
    ):
        if re.search(rf"\b{re.escape(code)}\b|_{re.escape(code)}|_?{re.escape(code)}_?", n):
            # Channel labels often say "87" without T/L/B/G — default to 87T.
            if code == "87":
                return "87T"
            return code
    return None


def observations_from_timeline(
    timeline: list[TimelineEvent],
) -> dict[str, ElementObservation]:
    """Infer per-element pickup/trip from timeline digital events."""
    obs: dict[str, ElementObservation] = {}
    for ev in timeline:
        src = ev.source
        channel = ""
        if src.startswith("digital:"):
            channel = src.split(":", 1)[1]
        code = _match_element_from_channel(channel) if channel else None
        if code is None:
            # Generic pickup/trip without element id → skip assignment
            continue
        o = obs.setdefault(code, ElementObservation(element=code))
        if channel and channel not in o.channel_evidence:
            o.channel_evidence.append(channel)
        if ev.event_type == "protection_pickup":
            o.pickup = True
            o.pickup_time_s = ev.timestamp
        elif ev.event_type == "protection_trip":
            o.trip = True
            o.trip_time_s = ev.timestamp
        elif ev.event_type == "reclose" and code == "79":
            o.trip = True
            o.trip_time_s = ev.timestamp
        elif ev.event_type == "lockout" and code == "86":
            o.trip = True
            o.trip_time_s = ev.timestamp
    return obs


def elements_from_uploaded_files(
    *,
    timeline: list[TimelineEvent],
    setting_candidates: list[SettingRecord],
    digital_channel_names: Optional[list[str]] = None,
) -> list[str]:
    """ANSI codes to assess from uploaded files.

    Prefer elements that appear in COMTRADE digitals (observable). When digitals
    exist, settings-only codes without a matching digital are skipped — those
    cannot be consistency-checked and only create UNVERIFIABLE noise.
    """
    settings_codes: set[str] = set()
    for rec in setting_candidates:
        el = (rec.element or "").strip().upper()
        if el and el != "GENERAL" and get_element(el) is not None:
            settings_codes.add(el)

    names = list(digital_channel_names or [])
    for ev in timeline:
        src = getattr(ev, "source", "") or ""
        if src.startswith("digital:"):
            names.append(src.split(":", 1)[1])

    digital_codes: set[str] = set()
    for name in names:
        code = _match_element_from_channel(str(name))
        if code and get_element(code) is not None:
            digital_codes.add(code)

    if digital_codes:
        # Digitals drive the check set; keep settings∩digitals when both exist
        overlap = settings_codes & digital_codes
        return sorted(overlap or digital_codes)
    return sorted(settings_codes)


def _seed_observations_from_channels(
    obs_map: dict[str, ElementObservation],
    digital_channel_names: Optional[list[str]],
) -> None:
    """If a digital channel exists for an element but never asserted, treat as not operated."""
    for name in digital_channel_names or []:
        code = _match_element_from_channel(str(name))
        if not code:
            continue
        o = obs_map.setdefault(code, ElementObservation(element=code))
        if name and name not in o.channel_evidence:
            o.channel_evidence.append(str(name))
        # Channel present in file → default False unless timeline set True
        if o.pickup is None:
            o.pickup = False
        if o.trip is None:
            o.trip = False


class ProtectionRuleEngine:
    """Load YAML rules and assess modular protection elements."""

    def __init__(self, rules_root: Path | None = None) -> None:
        self.rules_root = rules_root or (resolve_rules_root() / "protection")
        self.rule_configs = _load_rule_configs()

    def assess(
        self,
        *,
        timeline: list[TimelineEvent],
        setting_candidates: list[SettingRecord],
        electrical: Optional[dict[str, Any]] = None,
        elements: Optional[list[str]] = None,
        digital_channel_names: Optional[list[str]] = None,
    ) -> ProtectionEngineResult:
        electrical = electrical or {}
        obs_map = observations_from_timeline(timeline)
        _seed_observations_from_channels(obs_map, digital_channel_names)
        # Also seed from timeline digital sources not in the channel list
        timeline_names = [
            (getattr(ev, "source", "") or "").split(":", 1)[1]
            for ev in timeline
            if (getattr(ev, "source", "") or "").startswith("digital:")
        ]
        if timeline_names:
            _seed_observations_from_channels(obs_map, timeline_names)
        result = ProtectionEngineResult()

        if not self.rule_configs:
            result.limitations.append("Protection rules NOT AVAILABLE at expected path")

        if elements is not None:
            codes = list(elements)
        else:
            # Only elements present in uploaded settings / COMTRADE digitals —
            # never the full ANSI catalog (avoids mass UNVERIFIABLE noise).
            codes = elements_from_uploaded_files(
                timeline=timeline,
                setting_candidates=setting_candidates,
                digital_channel_names=digital_channel_names,
            )
            if not codes:
                result.limitations.append(
                    "No protection elements found in uploaded settings or COMTRADE digitals"
                )

        for code in codes:
            element = get_element(code)
            if element is None:
                result.limitations.append(f"Element module NOT AVAILABLE: {code}")
                continue

            obs = obs_map.get(code, ElementObservation(element=code))
            # Resolve common settings
            resolutions: dict[str, SettingResolution] = {}
            settings_vals: dict[str, Any] = {}
            for param in ("enabled", "pickup", "time_dial", "pickup_current", "zone1_reach", "curve"):
                res = resolve_setting(param, setting_candidates, element=code)
                resolutions[param] = res
                if param == "enabled":
                    settings_vals["enabled"] = (
                        res.enabled if res.enabled is not None else res.value
                    )
                else:
                    settings_vals[param] = res.value

            # If no digital observation, leave pickup/trip as None (UNKNOWN)
            ctx = ElementContext(
                observations=obs,
                settings=settings_vals,
                setting_resolutions=resolutions,
                electrical=electrical,
                timeline=[e.to_dict() for e in timeline],
                rule_config=self.rule_configs.get(code, {}),
            )
            assessment = element.assess(ctx)
            if code in self.rule_configs:
                assessment.metadata["rule_id"] = self.rule_configs[code].get("rule_id")
                assessment.metadata["rule_version"] = self.rule_configs[code].get("version")
            result.assessments.append(assessment)

        versions = [
            str(c.get("version"))
            for c in self.rule_configs.values()
            if c.get("version")
        ]
        if versions:
            result.rules_version = versions[0]
        return result
