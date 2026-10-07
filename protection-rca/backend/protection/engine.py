"""Modular protection rule engine."""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

from common.rules_path import load_yaml, resolve_rules_root
from event_reconstruction.timeline import TimelineEvent
from protection.elements.base_dispatch import get_element
from protection.channel_ansi import match_ansi_from_channel
from protection.models import (
    ElementContext,
    ElementObservation,
    ProtectionAssessment,
)
from protection.operate_evidence import (
    digital_channel_from_source,
    is_assertable_timeline_event,
    is_digital_timeline_source,
    operate_evidence_token,
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
    """Map vendor digital / fault channel names to ANSI (see protection.channel_ansi)."""
    return match_ansi_from_channel(name)


def _infer_elements_from_electrical(electrical: Optional[dict[str, Any]]) -> list[str]:
    """When only a general trip contact exists, seed likely OC/EF from electrical."""
    elec = electrical or {}
    codes: list[str] = []
    faultish = bool(
        elec.get("fault_indicated")
        or elec.get("current_increase")
        or elec.get("trip_command")
    )
    if not faultish:
        return codes
    codes.extend(["50", "51"])
    # Sequence / residual hints when present on electrical payload
    i0 = elec.get("I0")
    if i0 is None:
        feat = elec.get("fault_features") if isinstance(elec.get("fault_features"), dict) else {}
        i0 = feat.get("I0")
    try:
        if i0 is not None and float(i0) > 0:
            codes.extend(["50N", "51N"])
    except (TypeError, ValueError):
        pass
    i2 = elec.get("I2")
    try:
        if i2 is not None and float(i2) > 0:
            codes.append("46")
    except (TypeError, ValueError):
        pass
    out: list[str] = []
    for c in codes:
        if get_element(c) is not None and c not in out:
            out.append(c)
    return out


def _attribute_orphan_trips(
    obs: dict[str, ElementObservation],
    orphan_trips: list[TimelineEvent],
    *,
    electrical: Optional[dict[str, Any]] = None,
) -> None:
    """Map general trip contacts (TRIP_CMD, TRIP) onto pickup element(s).

    Vendor COMTRADE often records a shared trip output without an ANSI code in
    the channel name. Attribute that assert to *existing digital pickups* only.
    Never invent 50/51/… from electrical alone — that shows unwanted protection
    with no element evidence.
    """
    del electrical  # kept for call-site compatibility; no longer seeds operate
    for ev in orphan_trips:
        src = getattr(ev, "source", "") or ""
        if not is_digital_timeline_source(src):
            continue
        channel = digital_channel_from_source(src)
        t_trip = float(ev.timestamp)
        # Only pickups that already have DR channel evidence
        candidates = [
            o
            for o in obs.values()
            if o.pickup
            and o.channel_evidence
            and not o.trip
            and (o.pickup_time_s is None or float(o.pickup_time_s) <= t_trip + 1e-9)
        ]
        if not candidates:
            candidates = [
                o
                for o in obs.values()
                if o.pickup
                and o.channel_evidence
                and (o.pickup_time_s is None or float(o.pickup_time_s) <= t_trip + 1e-9)
            ]
        if not candidates:
            continue
        candidates.sort(
            key=lambda o: (
                0
                if o.pickup_time_s is None or float(o.pickup_time_s) <= t_trip + 1e-9
                else 1,
                abs(float(o.pickup_time_s) - t_trip)
                if o.pickup_time_s is not None
                else 0.0,
                -(float(o.pickup_time_s) if o.pickup_time_s is not None else 0.0),
            ),
        )
        shared = bool(
            re.search(
                r"TRIP_?CMD|GENERAL\s*TRIP|\bPTRC\d*\b|^TRIP$",
                channel or "",
                re.I,
            )
        )
        if shared and len(candidates) > 1:
            targets = [c for c in candidates if not c.trip] or [candidates[0]]
        else:
            targets = [candidates[0]]
        for o in targets:
            o.trip = True
            o.trip_time_s = t_trip
            if channel and channel not in o.channel_evidence:
                o.channel_evidence.append(channel)


def observations_from_timeline(
    timeline: list[TimelineEvent],
    *,
    digital_map: Optional[dict[str, Any]] = None,
    electrical: Optional[dict[str, Any]] = None,
) -> dict[str, ElementObservation]:
    """Infer per-element pickup/trip from timeline digital events / DR targets."""
    from protection.digital_targets import resolve_digital_target

    obs: dict[str, ElementObservation] = {}
    orphan_trips: list[TimelineEvent] = []
    for ev in timeline:
        src = ev.source
        # Industry practice: COMTRADE digital OR clear relay SER / event report
        if not is_assertable_timeline_event(ev):
            continue
        meta = ev.metadata if isinstance(ev.metadata, dict) else {}
        channel = digital_channel_from_source(src)
        # For SER/report, use signal/label for ANSI / reclose pattern matching
        name_for_match = channel or str(
            meta.get("point_tag") or meta.get("signal") or meta.get("label") or ""
        ).strip()
        evid_token = operate_evidence_token(ev)
        if not evid_token:
            continue

        code = str(meta.get("element") or "").upper().strip() or None
        if not code and name_for_match:
            _, mapped = resolve_digital_target(name_for_match, digital_map=digital_map)
            code = mapped
        if not code and name_for_match:
            code = _match_element_from_channel(name_for_match)

        # Inhibit / blocked AR is scheme status — NOT an autoreclose pickup
        _ar_inhibit = bool(
            name_for_match
            and re.search(
                r"INHIBIT\s*AR|AR_?INHIBIT|AR\s*INHIBIT|79\s*INHIBIT|INHIBIT.?RECLOSE",
                name_for_match,
                re.I,
            )
        )
        _reclose_operate = bool(
            name_for_match
            and not _ar_inhibit
            and re.search(
                r"AUTO.?RECLOSE|RECLOSE|\bRREC\d*\b|INITIATE_?AR|"
                r"\b79\s*(?:AR|RECLOSE|RREC)\b|"
                r"\bAR\s*(?:INIT|CLOSE|ON|OFF|SUCCESS)",
                name_for_match,
                re.I,
            )
        )
        # Autoreclose (79) only on clear initiate / close / success — never inhibit,
        # and never from bare map-backed digital without operate wording.
        if ev.event_type == "reclose" or code == "79":
            if _ar_inhibit:
                continue
            if not _reclose_operate:
                continue
            o79 = obs.setdefault("79", ElementObservation(element="79"))
            if evid_token not in o79.channel_evidence:
                o79.channel_evidence.append(evid_token)
            # Record as observed scheme activity (pickup flag = digital asserted);
            # persist layer stores operation_type RECLOSE, not fault PICKUP.
            o79.pickup = True
            if o79.pickup_time_s is None:
                o79.pickup_time_s = ev.timestamp
            continue

        if code is None:
            # Orphan general trip contacts — COMTRADE only (attribute to digital pickups)
            if is_digital_timeline_source(src) and ev.event_type in (
                "protection_trip",
                "breaker_trip_command",
            ):
                orphan_trips.append(ev)
            continue
        # Blocking / restraint asserts are not operate pickups (except 68/78 scheme)
        role = str(meta.get("target_role") or "").upper()
        if role == "BLOCK" and code not in ("68", "78"):
            continue
        if (
            name_for_match
            and re.search(r"\bBLOCK\b|\bBLK\b|INRUSH", name_for_match, re.I)
            and code not in ("68", "78")
            and ev.event_type == "protection_pickup"
        ):
            continue
        o = obs.setdefault(code, ElementObservation(element=code))
        if evid_token not in o.channel_evidence:
            o.channel_evidence.append(evid_token)
        if ev.event_type == "protection_pickup":
            o.pickup = True
            o.pickup_time_s = ev.timestamp
        elif ev.event_type == "protection_trip":
            o.trip = True
            o.trip_time_s = ev.timestamp
        elif ev.event_type == "lockout" and code == "86":
            o.trip = True
            o.trip_time_s = ev.timestamp
    _attribute_orphan_trips(obs, orphan_trips, electrical=electrical)
    return obs


def elements_from_uploaded_files(
    *,
    timeline: list[TimelineEvent],
    setting_candidates: list[SettingRecord],
    digital_channel_names: Optional[list[str]] = None,
    digital_map: Optional[dict[str, Any]] = None,
) -> list[str]:
    """ANSI codes to assess from uploaded files.

    Prefer elements that appear in COMTRADE digitals (observable). When digitals
    exist, settings-only codes without a matching digital are skipped — those
    cannot be consistency-checked and only create UNVERIFIABLE noise.
    """
    from protection.digital_targets import resolve_digital_target

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
        _, mapped = resolve_digital_target(str(name), digital_map=digital_map)
        code = mapped or _match_element_from_channel(str(name))
        if code and get_element(code) is not None:
            digital_codes.add(code)

    if digital_codes:
        overlap = settings_codes & digital_codes
        return sorted(overlap or digital_codes)
    return sorted(settings_codes)


def _seed_observations_from_channels(
    obs_map: dict[str, ElementObservation],
    digital_channel_names: Optional[list[str]],
    *,
    digital_map: Optional[dict[str, Any]] = None,
) -> None:
    """Ensure CFG-mapped elements exist for assessment — do NOT invent operate evidence.

    Never append unasserted CFG names to ``channel_evidence`` (that falsely
    satisfies evidence gates). Only mark pickup/trip False when still unknown.
    """
    from protection.digital_targets import resolve_digital_target

    for name in digital_channel_names or []:
        _, mapped = resolve_digital_target(str(name), digital_map=digital_map)
        code = mapped or _match_element_from_channel(str(name))
        if not code:
            continue
        o = obs_map.setdefault(code, ElementObservation(element=code))
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
        digital_map: Optional[dict[str, Any]] = None,
    ) -> ProtectionEngineResult:
        electrical = electrical or {}
        obs_map = observations_from_timeline(
            timeline, digital_map=digital_map, electrical=electrical
        )
        _seed_observations_from_channels(
            obs_map, digital_channel_names, digital_map=digital_map
        )
        timeline_names = [
            (getattr(ev, "source", "") or "").split(":", 1)[1]
            for ev in timeline
            if (getattr(ev, "source", "") or "").startswith("digital:")
        ]
        if timeline_names:
            _seed_observations_from_channels(
                obs_map, timeline_names, digital_map=digital_map
            )
        result = ProtectionEngineResult()

        if not self.rule_configs:
            result.limitations.append("Protection rules NOT AVAILABLE at expected path")

        if elements is not None:
            codes = list(elements)
        else:
            codes = elements_from_uploaded_files(
                timeline=timeline,
                setting_candidates=setting_candidates,
                digital_channel_names=digital_channel_names,
                digital_map=digital_map,
            )
            # Include elements that actually asserted on DR digitals
            for code, o in obs_map.items():
                if code not in codes and get_element(code) is not None:
                    if o.pickup or o.trip or o.channel_evidence:
                        codes.append(code)
            # Settings/electrical-only: assess for consistency, never as operated
            if not codes:
                for code in _infer_elements_from_electrical(electrical):
                    if code not in codes:
                        codes.append(code)
                        obs_map.setdefault(code, ElementObservation(element=code))
            codes = sorted(codes)
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
