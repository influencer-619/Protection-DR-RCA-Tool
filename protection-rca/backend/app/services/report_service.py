"""Report generation — JSON + Jinja HTML + PDF packaging."""

from __future__ import annotations

import hashlib
import io
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    ComtradeFile,
    ConsistencyFinding,
    EngineerReview,
    Event,
    EventFile,
    EventTimeline,
    Evidence,
    FaultClassification,
    Measurement,
    ProtectionOperation,
    RcaHypothesis,
    Report,
)
from app.services.audit_service import write_audit
from app.services.storage import StorageService

logger = logging.getLogger(__name__)


def _conf_label(v: Any) -> str:
    if v is None:
        return "INCONCLUSIVE"
    if isinstance(v, str):
        return v
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if f >= 0.85:
        return "HIGH"
    if f >= 0.55:
        return "MEDIUM"
    if f >= 0.25:
        return "LOW"
    return "INCONCLUSIVE"


def _format_fault_distance(fault: dict[str, Any]) -> str | None:
    """Return a location string when calculable; None when not applicable / not attempted."""
    evidence = fault.get("evidence") if isinstance(fault.get("evidence"), dict) else {}
    if evidence.get("distance_applicable") is False:
        return None
    dist = fault.get("distance")
    if isinstance(dist, dict):
        if str(dist.get("status") or "").upper() in ("NOT_APPLICABLE", "N/A", "NA"):
            return None
        if dist.get("value_km") is not None and evidence.get("distance_applicable") is not False:
            unit = dist.get("unit") or "km"
            method = dist.get("method") or ""
            suffix = f" ({method})" if method else ""
            return f"{dist['value_km']} {unit}{suffix}"
        status = str(dist.get("status") or "").upper()
        if status in ("NOT_CALCULABLE", "INCONCLUSIVE") or dist.get("reason"):
            if evidence.get("distance_applicable") is True:
                reason = dist.get("reason") or "insufficient validated inputs"
                return f"FAULT DISTANCE: NOT CALCULABLE — {reason}"
        return None
    return None


def _plant_from_event(event: Event) -> tuple[str | None, str | None, dict[str, Any]]:
    extra = event.extra if isinstance(event.extra, dict) else {}
    plant = extra.get("plant_labels") if isinstance(extra.get("plant_labels"), dict) else {}
    ss = plant.get("substation_name") or extra.get("substation_name")
    bay = plant.get("bay_name") or extra.get("bay_name")
    relay = plant.get("relay_tag") or extra.get("relay_tag")
    asset_parts = [
        p
        for p in (
            f"Substation: {ss}" if ss else None,
            f"Bay: {bay}" if bay else None,
            f"Feeder: {event.feeder}" if event.feeder else None,
            (
                f"Nominal voltage: {event.nominal_voltage_kv} kV"
                if event.nominal_voltage_kv is not None
                else None
            ),
        )
        if p
    ]
    relay_parts = [f"Relay tag: {relay}"] if relay else []
    return (
        ", ".join(asset_parts) or None,
        ", ".join(relay_parts) or None,
        extra,
    )


def _fmt_report_dt(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        try:
            return value.strftime("%d %b %Y %H:%M:%S")
        except Exception:  # noqa: BLE001
            pass
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        try:
            from datetime import datetime

            return datetime.fromisoformat(text.replace("Z", "+00:00")).strftime(
                "%d %b %Y %H:%M:%S"
            )
        except Exception:  # noqa: BLE001
            return text.replace("T", " ").split(".")[0]
    return text


def _looks_like_file_batch_desc(desc: str | None) -> bool:
    if not desc or not str(desc).strip():
        return True
    text = str(desc).strip()
    if text.lower().startswith("upload batch"):
        return True
    if text.lower().startswith("iec 61850"):
        return False
    exts = (".cfg", ".dat", ".cff", ".json", ".txt", ".csv", ".pdf", ".zip", ".set", ".rdb")
    hits = sum(1 for e in exts if e in text.lower())
    return hits >= 2


_EVENT_TYPE_LABELS = {
    "protection_pickup": "Protection pickup",
    "protection_trip": "Protection trip",
    "breaker_trip_command": "Breaker trip command",
    "52a_change": "Breaker auxiliary (52a)",
    "52b_change": "Breaker auxiliary (52b)",
    "current_increase": "Current increase",
    "current_interruption": "Current interruption",
    "voltage_change": "Voltage change",
    "fault_inception": "Fault inception",
    "reclose": "Reclose",
    "lockout": "Lockout",
}


def _timeline_value_display(payload: dict[str, Any], source: str = "") -> str:
    """Human value for report timeline: analog RMS/sample or digital 0→1."""
    meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    if not meta and isinstance(payload, dict):
        meta = payload
    unit = str(meta.get("unit") or "").strip()

    def _num(v: Any) -> str | None:
        try:
            if v is None:
                return None
            x = float(v)
            if abs(x) >= 1000 or (0 < abs(x) < 0.01):
                return f"{x:.4g}"
            return f"{x:.3f}".rstrip("0").rstrip(".")
        except (TypeError, ValueError):
            return None

    rms = _num(meta.get("value_rms"))
    if rms is not None:
        return f"{rms} {unit}".strip() if unit else f"{rms} RMS"
    sample = _num(meta.get("value"))
    if sample is not None and str(source).startswith("analog:"):
        return f"{sample} {unit}".strip() if unit else sample
    if "from" in meta and "to" in meta:
        return f"{meta.get('from')} → {meta.get('to')}"
    if meta.get("asserted") is True:
        return "Asserted"
    if meta.get("asserted") is False:
        return "De-asserted"
    # Fallback: baseline/threshold for older persisted analog events
    base = _num(meta.get("baseline_rms"))
    thr = _num(meta.get("threshold"))
    if base is not None and thr is not None:
        u = f" {unit}" if unit else ""
        return f"baseline {base}{u}, thr {thr}{u}"
    return "—"


def _humanize_event_type(value: Any) -> str:
    key = str(value or "").strip()
    if not key:
        return "—"
    low = key.lower().replace("-", "_").replace(" ", "_")
    if low in _EVENT_TYPE_LABELS:
        return _EVENT_TYPE_LABELS[low]
    if key in _EVENT_TYPE_LABELS:
        return _EVENT_TYPE_LABELS[key]
    return key.replace("_", " ").strip().title()


# Engineer key sequence — operate-critical steps only (Summary / Report §5)
_KEY_SEQUENCE_TYPES = frozenset(
    {
        "fault_inception",
        "protection_pickup",
        "protection_trip",
        "breaker_trip_command",
        "52a_change",
        "52b_change",
        "current_interruption",
        "reclose",
        "lockout",
        "intertrip",
    }
)


def _key_sequence_rows(timeline_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """First occurrence of each operate-critical step (chronological)."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in sorted(
        timeline_rows,
        key=lambda r: (
            float(r["timestamp"]) if r.get("timestamp") is not None else 1e18,
            str(r.get("event_type") or ""),
        ),
    ):
        et = str(row.get("event_type") or "").strip().lower().replace(" ", "_")
        if et not in _KEY_SEQUENCE_TYPES or et in seen:
            continue
        seen.add(et)
        out.append(row)
    return out


def _enrichment_token_bag(enrich: dict[str, Any] | None) -> set[str]:
    bag: set[str] = set()
    if not isinstance(enrich, dict):
        return bag
    for t in enrich.get("tokens") or []:
        bag.add(str(t))
    deep = enrich.get("ladder_deep") if isinstance(enrich.get("ladder_deep"), dict) else {}
    for t in deep.get("tokens") or []:
        bag.add(str(t))
    for t in enrich.get("matrix_traces") or []:
        # traces are free text — also scan for receive/send cues
        u = str(t).upper()
        if "INTERTRIP" in u and "RECEIV" in u:
            bag.add("intertrip_receive_observed")
        if "INTERTRIP" in u and "SEND" in u:
            bag.add("intertrip_send_observed")
    return bag


def _intertrip_summary(
    timeline_rows: list[dict[str, Any]],
    enrich: dict[str, Any] | None,
) -> str:
    bag = _enrichment_token_bag(enrich)
    rx = "intertrip_receive_observed" in bag
    send = "intertrip_send_observed" in bag
    if not rx and not send:
        blob_parts: list[str] = []
        for row in timeline_rows:
            if str(row.get("event_type") or "").lower() != "intertrip":
                continue
            blob_parts.append(
                " ".join(
                    str(x)
                    for x in (
                        row.get("label"),
                        row.get("source"),
                        row.get("value"),
                        row.get("event_type"),
                    )
                    if x
                )
            )
        blob = " ".join(blob_parts).upper()
        if not blob and "intertrip_signal_observed" not in bag:
            return "None asserted"
        rx = bool(re.search(r"RECEIV|INTERTRIP_RX|\bTT_?RX\b|\bBF_?RX\b", blob))
        send = bool(
            re.search(r"INTERTRIP_SEND|TT_?SEND|TRANSFER.?TRIP.?SEND|\bBF_?TX\b", blob)
        )
        if not rx and not send and (blob or "intertrip_signal_observed" in bag):
            return "Asserted"
    if rx and not send:
        return "Received (backup / upstream clearance)"
    if send and not rx:
        return "Sent (LBB / transfer trip)"
    if rx and send:
        return "Received + send asserted"
    return "Asserted"


def _humanize_token(value: Any) -> str:
    key = str(value or "").strip()
    if not key or key in ("—", "-", "N/A", "NA"):
        return "—"
    labels = {
        "fault_classified": "Fault type classified",
        "fault_classified_strong": "Strong fault classification",
        "current_increase_observed": "Fault current increase observed",
        "protection_operated": "Protection trip asserted",
        "protection_responded": "Protection response asserted",
        "protection_pickup_asserted": "Protection pickup asserted",
        "protection_trip_asserted": "Protection trip asserted",
        "protection_pickup_with_trip": "Protection pickup with trip",
        "settings_behavior_consistent": "Settings vs behaviour consistent",
        "ground_involved": "Ground / earth involved",
        "distance_element_operated": "Distance element 21 (Distance protection) operated",
        "distance_estimate_available": "Location estimate available",
        "loop_impedance_available": "Loop impedance available",
        "scheme_distance": "Distance scheme context",
        "differential_operated": "Differential element 87 (Differential) trip asserted",
        "transformer_diff_operated": "Transformer differential 87T trip asserted",
        "transformer_diff_picked_up": "Transformer differential 87T pickup asserted",
        "bus_diff_operated": "Bus differential 87B trip asserted",
        "bus_diff_picked_up": "Bus differential 87B pickup asserted",
        "generator_diff_operated": "Generator differential 87G trip asserted",
        "generator_diff_picked_up": "Generator differential 87G pickup asserted",
        "line_diff_operated": "Line differential 87L trip asserted",
        "line_diff_picked_up": "Line differential 87L pickup asserted",
        "magnetizing_inrush_possible": "Magnetizing inrush / charging (H2)",
        "motor_start_possible": "Motor start / starting-current signature",
        "motor_protection_present": "Motor-protection digitals present",
        "motor_element_operated": "Motor element 46/48/49 trip asserted",
        "motor_element_picked_up": "Motor element 46/48/49 pickup asserted (no trip)",
        "overcurrent_element_operated": "50/51 (Instantaneous / time overcurrent) trip asserted",
        "overcurrent_element_picked_up": "50/51 (Instantaneous / time overcurrent) pickup asserted (no trip)",
        "earth_fault_element_operated": "50N/51N/67N (Earth-fault / directional earth) trip asserted",
        "earth_fault_element_picked_up": "50N/51N/67N (Earth-fault / directional earth) pickup asserted (no trip)",
        "directional_element_operated": "67 (Directional overcurrent) trip asserted",
        "directional_element_picked_up": "67 (Directional overcurrent) pickup asserted (no trip)",
        "scheme_motor": "Motor protection scheme",
        "through_fault_excluded": "Through-fault excluded",
        "cable_asset_confirmed": "Cable asset confirmed",
        "protection_sequence": "Protection sequence",
        "enabled_vs_pickup": "Enabled vs pickup",
        "enabled_vs_trip": "Enabled vs trip",
        "pickup_vs_trip": "Pickup vs trip",
        "electrical_no_fault": "Electrical evidence indicates non-fault event",
        "dfr_non_fault_event": "DFR classed as non-fault (energization/motor/switching/disturbance)",
        "event_class_FAULT": "DFR event class: FAULT",
        "event_class_ENERGIZATION": "DFR event class: ENERGIZATION (inrush/charging)",
        "event_class_MOTOR_START": "DFR event class: MOTOR_START",
        "event_class_SWITCHING": "DFR event class: SWITCHING",
        "event_class_DISTURBANCE": "DFR event class: DISTURBANCE",
        "event_class_UNKNOWN": "DFR event class: UNKNOWN",
    }
    if key in labels:
        return labels[key]
    if key.startswith("event_class_"):
        return "DFR event class: " + key.replace("event_class_", "").replace("_", " ")
    if key.startswith("scheme_"):
        return "Scheme: " + key.replace("scheme_", "").replace("_", " ")
    return key.replace("_", " ")


def _yes_no(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    if value in (None, "", "—"):
        return "—"
    return str(value)


def _format_score_pct(value: Any) -> str:
    """Render 0–1 scores (or already-percent values) as percentage text."""
    if value is None:
        return "—"
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return "—"
        if s.endswith("%"):
            return s
        try:
            value = float(s)
        except ValueError:
            return s
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    if 0.0 <= f <= 1.0:
        f *= 100.0
    # Prefer one decimal for non-integers, else whole percent
    if abs(f - round(f)) < 1e-9:
        return f"{int(round(f))}%"
    return f"{f:.1f}%"


def _pct_scores_in_rca(rca: Any) -> None:
    if not isinstance(rca, dict):
        return
    primary = rca.get("primary")
    if isinstance(primary, dict) and "score" in primary:
        primary["score"] = _format_score_pct(primary.get("score_raw", primary.get("score")))
    hyps = rca.get("hypotheses")
    if isinstance(hyps, list):
        for h in hyps:
            if isinstance(h, dict) and "score" in h:
                h["score"] = _format_score_pct(h.get("score_raw", h.get("score")))


def _format_engineer_review(review: EngineerReview | None) -> str:
    """Human-readable disposition for the report Engineer Review section."""
    if review is None:
        return "PENDING"
    action = (review.action or "PENDING").strip().upper()
    lines = [action]
    if review.reviewed_at is not None:
        ts = review.reviewed_at
        if getattr(ts, "tzinfo", None) is None:
            lines.append(f"Reviewed at: {ts.isoformat()}Z")
        else:
            lines.append(
                f"Reviewed at: {ts.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
            )
    if review.decision_state:
        lines.append(f"Decision state: {review.decision_state}")
    if review.comments:
        lines.append(f"Comments: {review.comments}")
    mods = review.modifications
    if isinstance(mods, dict) and mods:
        notes = mods.get("notes") or mods.get("note")
        if notes:
            lines.append(f"Modifications: {notes}")
        else:
            lines.append(f"Modifications: {json.dumps(mods, default=str)}")
    elif mods:
        lines.append(f"Modifications: {mods}")
    return "\n".join(lines)


def _rebuild_analysis_from_db(
    event: Event,
    *,
    faults: list[FaultClassification],
    hyps: list[RcaHypothesis],
    findings: list[ConsistencyFinding],
    timeline: list[EventTimeline],
    ops: list[ProtectionOperation],
    evidence: list[Evidence],
    comtrades: list[ComtradeFile],
    files: list[EventFile],
    measurements: list[Measurement] | None = None,
    latest_review: EngineerReview | None = None,
) -> dict[str, Any]:
    asset_line, relay_line, extra = _plant_from_event(event)
    # Fall back to COMTRADE station/device when plant labels empty
    if comtrades:
        ct0 = comtrades[0]
        if not asset_line and ct0.station_name:
            asset_line = f"Substation: {ct0.station_name}"
            if event.feeder:
                asset_line += f", Feeder: {event.feeder}"
        if not relay_line and ct0.recording_device:
            relay_line = f"Relay / recording device: {ct0.recording_device}"

    desc = event.description
    if _looks_like_file_batch_desc(desc):
        desc = None

    file_inventory = [
        {
            "filename": f.original_filename,
            "type": f.source_type or "OTHER",
            "size_bytes": f.file_size,
            "sha256": (f.sha256 or "")[:16] + "…" if f.sha256 else "—",
        }
        for f in files
    ]

    primary_fault = next((f for f in faults if f.is_primary), faults[0] if faults else None)
    fault_dict: dict[str, Any] = {}
    if primary_fault is not None:
        feat = primary_fault.features if isinstance(primary_fault.features, dict) else {}
        dist_detail = feat.get("distance_detail") if isinstance(feat.get("distance_detail"), dict) else {}
        distance_applicable = feat.get("distance_applicable")
        if distance_applicable is None:
            # Legacy rows without the flag: never unlock km from stored distance alone
            distance_applicable = False
        else:
            distance_applicable = bool(distance_applicable)
        if str(dist_detail.get("status") or "").upper() == "NOT_APPLICABLE":
            distance_applicable = False
        location_attempted = bool(
            distance_applicable
            and (
                primary_fault.distance_km is not None
                or primary_fault.location_method
                or dist_detail.get("algorithms")
                or str(dist_detail.get("status") or "").upper()
                in ("OK", "NOT_CALCULABLE", "INCONCLUSIVE")
            )
        )
        if not distance_applicable:
            dist_status = "NOT_APPLICABLE"
        elif primary_fault.distance_km is not None:
            dist_status = "OK"
        elif location_attempted:
            dist_status = str(dist_detail.get("status") or "NOT_CALCULABLE")
        else:
            dist_status = "NOT_APPLICABLE"
        expl = primary_fault.explanation or ""
        if not distance_applicable and expl:
            parts = [p.strip() for p in expl.split(";") if p.strip()]
            parts = [
                p
                for p in parts
                if "FAULT DISTANCE" not in p.upper()
                and "Z1/KM" not in p.upper()
                and "LINE Z1" not in p.upper()
            ]
            expl = "; ".join(parts)
        evc = (
            feat.get("event_classification")
            if isinstance(feat.get("event_classification"), dict)
            else {}
        )
        event_class = feat.get("event_class") or evc.get("event_class")
        fault_dict = {
            "fault_type": primary_fault.fault_type,
            "status": primary_fault.status,
            "confidence": primary_fault.confidence_level or _conf_label(primary_fault.confidence),
            "event_class": event_class,
            "event_class_status": feat.get("event_class_status") or evc.get("status"),
            "involved_phases": primary_fault.involved_phases,
            "ground_involved": primary_fault.ground_involved,
            "evidence": {**feat, "distance_applicable": distance_applicable},
            "distance": {
                "value_km": primary_fault.distance_km if distance_applicable else None,
                "method": primary_fault.location_method if distance_applicable else None,
                "status": dist_status,
                "reason": dist_detail.get("reason") if location_attempted else None,
                "algorithms": dist_detail.get("algorithms") if distance_applicable else [],
            },
            "limitations": [expl] if expl else [],
            "distance_display": None,
        }
        fault_dict["distance_display"] = _format_fault_distance(fault_dict)

    # Deduplicate protection assessments by element (prefer TRIP > PICKUP > ASSESSMENT)
    rank = {"TRIP": 0, "PICKUP": 1, "ASSESSMENT": 2}
    by_el: dict[str, dict[str, Any]] = {}
    for op in ops:
        details = op.details if isinstance(op.details, dict) else {}
        row = {
            "element": op.element,
            "enabled": details.get("enabled"),
            "pickup": details.get("pickup")
            if "pickup" in details
            else (op.operation_type == "PICKUP"),
            "trip": details.get("trip") if "trip" in details else (op.operation_type == "TRIP"),
            "expected_operation": details.get("expected_operation"),
            "actual_operation": details.get("actual_operation"),
            "consistency": details.get("consistency"),
            "confidence": details.get("confidence") or _conf_label(op.confidence),
        }
        if details:
            row = {**details, **{k: v for k, v in row.items() if v is not None}}
        prev = by_el.get(op.element)
        if prev is None or rank.get(op.operation_type, 9) < rank.get(
            str(prev.get("_op") or "ASSESSMENT"), 9
        ):
            row["_op"] = op.operation_type
            by_el[op.element] = row

    # Fill gaps from element consistency findings (not sequence / GENERAL)
    for f in findings:
        el = str(f.element or "UNKNOWN").strip()
        check = str(getattr(f, "check_type", None) or "").lower()
        if el.upper() == "GENERAL" or check == "protection_sequence":
            continue
        if el in by_el:
            if not by_el[el].get("consistency"):
                by_el[el]["consistency"] = f.status
            continue
        expected = f.expected if isinstance(f.expected, dict) else {}
        observed = f.observed if isinstance(f.observed, dict) else {}
        by_el[el] = {
            "element": el,
            "enabled": expected.get("enabled")
            if "enabled" in expected
            else observed.get("enabled"),
            "pickup": observed.get("pickup"),
            "trip": observed.get("trip"),
            "expected_operation": expected.get("operation") or expected.get("value") or "—",
            "actual_operation": observed.get("operation") or observed.get("value") or "—",
            "consistency": f.status,
            "confidence": _conf_label(f.confidence),
            "_op": "ASSESSMENT",
        }
    protection = []
    for r in by_el.values():
        if str(r.get("element") or "").upper() == "GENERAL":
            continue
        clean = {k: v for k, v in r.items() if k != "_op"}
        clean["enabled_display"] = _yes_no(clean.get("enabled"))
        clean["pickup_display"] = _yes_no(clean.get("pickup"))
        clean["trip_display"] = _yes_no(clean.get("trip"))
        act = str(clean.get("actual_operation") or "").upper()
        if act == "PICKED_UP":
            clean["actual_operation"] = "PICKED UP"
        elif act == "NOT_OPERATED":
            clean["actual_operation"] = "NOT OPERATED"
        elif act == "OPERATED":
            clean["actual_operation"] = "TRIPPED"
        protection.append(clean)
    from protection.operate_evidence import assessment_has_operate_evidence

    operated_elements = [
        str(p.get("element"))
        for p in protection
        if assessment_has_operate_evidence(p)
        and (
            p.get("trip") is True
            or str(p.get("actual_operation") or "").upper()
            in ("OPERATED", "TRIPPED", "TRIP", "TRUE", "PICKED UP", "PICKED_UP")
            or p.get("pickup") is True
        )
    ]

    timeline_rows = []
    for te in sorted(timeline, key=lambda x: (x.sequence or 0, x.t_us or 0)):
        payload = te.payload if isinstance(te.payload, dict) else {}
        ts = payload.get("timestamp")
        if ts is None and te.t_us is not None:
            ts = te.t_us / 1_000_000.0
        src = te.source or payload.get("source") or "COMTRADE"
        # Nested metadata may live under payload.metadata or payload itself
        value_txt = _timeline_value_display(payload, str(src))
        meta = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
        timeline_rows.append(
            {
                "event_type": te.event_type,
                "event_type_label": _humanize_event_type(te.event_type),
                "timestamp": float(ts) if ts is not None else 0.0,
                "source": src,
                "value": value_txt,
                "value_rms": meta.get("value_rms"),
                "unit": meta.get("unit"),
                "confidence": te.confidence
                if isinstance(te.confidence, str)
                else _conf_label(te.confidence)
                if te.confidence is not None
                else payload.get("confidence") or "INCONCLUSIVE",
                "label": te.label,
            }
        )

    # Key timings for the executive summary (pickup → trip → interrupt)
    timing: dict[str, Any] = {}
    for row in timeline_rows:
        et = str(row.get("event_type") or "")
        t = row.get("timestamp")
        if t is None:
            continue
        if et == "protection_pickup" and "pickup_s" not in timing:
            timing["pickup_s"] = t
        elif et == "protection_trip" and "trip_s" not in timing:
            timing["trip_s"] = t
        elif et == "52a_change" and "breaker_s" not in timing:
            timing["breaker_s"] = t
        elif et == "current_interruption" and "interrupt_s" not in timing:
            timing["interrupt_s"] = t
    if timing.get("pickup_s") is not None and timing.get("trip_s") is not None:
        timing["pickup_to_trip_ms"] = round(
            (float(timing["trip_s"]) - float(timing["pickup_s"])) * 1000.0, 1
        )
    if timing.get("trip_s") is not None and timing.get("interrupt_s") is not None:
        timing["trip_to_clear_ms"] = round(
            (float(timing["interrupt_s"]) - float(timing["trip_s"])) * 1000.0, 1
        )

    hyp_rows = []
    primary_hyp = None
    for h in hyps:
        raw = (h.extra or {}).get("raw") if isinstance(h.extra, dict) else None
        missing = None
        if isinstance(h.extra, dict):
            missing = h.extra.get("missing_evidence")
        if isinstance(raw, dict):
            missing = missing or raw.get("missing_evidence")
        supporting = h.supporting_evidence_ids or []
        missing_list = list(missing or [])
        chain = list(h.causal_chain or [])
        if not chain and isinstance(raw, dict):
            chain = list(raw.get("causal_chain") or [])
        row = {
            "hypothesis_id": h.hypothesis_code or h.title,
            "title": h.title,
            "status": h.status,
            "score": _format_score_pct(h.confidence),
            "score_raw": h.confidence,
            "confidence": h.confidence_level or _conf_label(h.confidence),
            "statement": h.statement,
            "explanation": h.explanation,
            "causal_chain": chain,
            "missing_evidence": missing_list,
            "missing_evidence_labels": [_humanize_token(x) for x in missing_list],
            "supporting_evidence": supporting,
            "supporting_evidence_labels": [_humanize_token(x) for x in supporting],
            "recommended_actions": h.recommended_actions or [],
        }
        hyp_rows.append(row)
        if primary_hyp is None or (h.rank or 99) < (primary_hyp.get("_rank") or 99):
            primary_hyp = {**row, "_rank": h.rank}

    if primary_hyp:
        primary_hyp.pop("_rank", None)

    evidence_rows = []
    for ev in evidence[:50]:
        refs = ev.references if isinstance(ev.references, dict) else {}
        raw = ev.raw if isinstance(ev.raw, dict) else {}
        evidence_rows.append(
            {
                "evidence_id": ev.evidence_key,
                "source_type": ev.source_type,
                "parameter": refs.get("parameter") or raw.get("parameter") or ev.title,
                "value": refs.get("value")
                if refs.get("value") is not None
                else raw.get("value") or ev.summary,
                "interpretation": ev.summary or raw.get("interpretation") or "",
                "confidence": _conf_label(ev.confidence),
            }
        )

    dq: dict[str, Any] = {
        "event_data_quality": event.data_quality or "NOT AVAILABLE",
        "comtrade": [],
    }
    for cf in comtrades[:3]:
        dq["comtrade"].append(
            {
                "station_name": cf.station_name,
                "recording_device": cf.recording_device,
                "sample_rate_hz": cf.sample_rate_hz,
                "total_samples": cf.total_samples,
                "analog_channel_count": cf.analog_channel_count,
                "digital_channel_count": cf.digital_channel_count,
                "validation_status": cf.validation_status,
                "data_quality": cf.data_quality,
                "parse_warnings": cf.parse_warnings,
                "start_timestamp": _fmt_report_dt(cf.start_timestamp),
            }
        )
    if not dq["comtrade"] and not event.data_quality:
        dq = {"status": "NOT AVAILABLE — re-run analysis after COMTRADE parse", "comtrade": []}

    def _bound_setting(value: object) -> Any:
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.upper().replace("_", " ") in {
            "N/A",
            "NA",
            "NONE",
            "MIXED",
            "NOT AVAILABLE",
            "NOT_AVAILABLE",
        }:
            return None
        return value if not isinstance(value, str) else text

    src = _bound_setting(extra.get("setting_source"))
    ver = _bound_setting(extra.get("setting_version"))
    for f in findings or []:
        if src is None:
            src = _bound_setting(getattr(f, "setting_source", None))
        if ver is None:
            ver = _bound_setting(getattr(f, "setting_version", None))
        if src and ver:
            break

    setting_ref = {
        "setting_source_used": src,
        "setting_version": ver,
        "setting_group": extra.get("setting_group"),
        "active_setting_group_verification": extra.get("active_group_status"),
        "setting_approval": extra.get("setting_approval"),
        "setting_file": extra.get("setting_file"),
        "param_count": extra.get("setting_param_count"),
        "explanation": extra.get("settings_file_verification_note"),
    }
    # Treat param_count=0 as empty so we don't keep a hollow table of dashes
    meaningful = [
        v
        for k, v in setting_ref.items()
        if k != "param_count" and v is not None and v != ""
    ]
    if not meaningful and not (setting_ref.get("param_count") or 0):
        setting_ref = {
            "status": "NOT AVAILABLE / NOT VERIFIED",
            "hint": "Upload relay_settings.json and re-run analysis",
        }

    # Electrical RMS from persisted measurements
    rms_summary: dict[str, Any] = {}
    sample_rate = None
    for m in measurements or []:
        q = str(m.quantity or "")
        if q.endswith("_rms") or m.algorithm == "electrical_analysis":
            name = q[:-4] if q.endswith("_rms") else q
            rms_summary[name] = {
                "value": m.value,
                "unit": m.unit,
                "status": m.quality or "OK",
            }
    if comtrades:
        sample_rate = comtrades[0].sample_rate_hz

    decision = {
        "state": event.decision_state or "ENGINEER_REVIEW_REQUIRED",
        "confidence": (
            (primary_hyp or {}).get("confidence")
            if primary_hyp
            else "INCONCLUSIVE"
        ),
        "recommended_actions": (primary_hyp or {}).get("recommended_actions")
        or [
            "Verify active setting group against event time",
            "Review consistency and protection operation tables",
            "Confirm plant labels and channel mapping",
        ],
        "requires_engineer_review": True,
    }

    limitations = list(extra.get("analysis_limitations") or [])
    limitations.append(
        "Report generated from structured analysis data only."
    )
    # ML/similarity honesty lives on supporting_scores / RCA page — not report banners
    _ml_sim_noise = (
        "ml anomaly scores unavailable",
        "historical similarity unavailable",
        "ml weight contribution",
        "similarity weight contribution",
        "ml result: not available",
        "similarity result: not available",
    )
    limitations = [
        lim
        for lim in limitations
        if not any(n in str(lim).lower() for n in _ml_sim_noise)
    ]
    # Drop legacy Z1 / FAULT DISTANCE noise when distance is out of scope
    if primary_fault is not None:
        feat = primary_fault.features if isinstance(primary_fault.features, dict) else {}
        dist_ok = feat.get("distance_applicable") is True
        if not dist_ok:
            limitations = [
                lim
                for lim in limitations
                if "FAULT DISTANCE" not in str(lim).upper()
                and "Z1/KM" not in str(lim).upper()
                and "LINE Z1" not in str(lim).upper()
                and "Fault location shown only when" not in str(lim)
            ]
        elif primary_fault.distance_km is None and (
            feat.get("location_method")
            or (isinstance(feat.get("distance_detail"), dict) and feat["distance_detail"].get("algorithms"))
        ):
            limitations.append(
                "Fault location shown only when calculable from validated line/CT-VT inputs."
            )

    plant_labels = extra.get("plant_labels") if isinstance(extra.get("plant_labels"), dict) else {}
    substation = plant_labels.get("substation_name") or extra.get("substation_name")
    bay = plant_labels.get("bay_name") or extra.get("bay_name")
    relay_tag = plant_labels.get("relay_tag") or extra.get("relay_tag")
    cascade = extra.get("cascade") if isinstance(extra.get("cascade"), dict) else {}
    multi_end = extra.get("multi_end") if isinstance(extra.get("multi_end"), dict) else {}
    is_cascade = bool(cascade.get("detected")) or "LBB" in str(
        cascade.get("mode") or ""
    ).upper()
    is_line = bool(multi_end.get("detected"))
    feeder_label = event.feeder
    ct0 = comtrades[0] if comtrades else None
    # DR time = relay disturbance only (event_datetime or COMTRADE start). Never use created_at.
    event_when = _fmt_report_dt(event.event_datetime) or (
        _fmt_report_dt(ct0.start_timestamp) if ct0 else None
    )
    created_when = _fmt_report_dt(event.created_at)

    if not desc:
        ft = (fault_dict or {}).get("fault_type")
        if ft and ft != "UNKNOWN":
            desc = f"{ft} disturbance on {event.feeder or 'feeder'} — protection RCA"
        else:
            desc = "Disturbance record analysis"

    report_kind = "Protection disturbance analysis report"

    ra_snap = extra.get("report_analysis") if isinstance(extra.get("report_analysis"), dict) else {}
    enrich = ra_snap.get("enrichment") if isinstance(ra_snap.get("enrichment"), dict) else {}
    matrix_block = ra_snap.get("matrix") if isinstance(ra_snap.get("matrix"), dict) else {}
    if not matrix_block and isinstance(cascade.get("rca"), dict):
        matrix_block = {
            "compound_class": cascade.get("compound_class"),
            "matched_scenario_id": cascade.get("matrix_scenario"),
            "traces": cascade.get("matrix_traces") or [],
        }
    compound_class = (
        enrich.get("compound_class")
        or matrix_block.get("compound_class")
        or cascade.get("compound_class")
    )
    matrix_scenario = (
        enrich.get("matrix_scenario")
        or matrix_block.get("matched_scenario_id")
        or cascade.get("matrix_scenario")
    )
    matrix_traces = list(
        enrich.get("matrix_traces")
        or matrix_block.get("traces")
        or cascade.get("matrix_traces")
        or []
    )[:16]
    key_seq = _key_sequence_rows(timeline_rows)
    intertrip_label = _intertrip_summary(timeline_rows, enrich)
    ladder_deep = enrich.get("ladder_deep") if isinstance(enrich.get("ladder_deep"), dict) else {}
    l2 = ladder_deep.get("l2_causality") if isinstance(ladder_deep.get("l2_causality"), dict) else {}

    return {
        "event": {
            "id": event.id,
            "event_id": event.event_id,
            "status": event.status,
            "decision_state": event.decision_state,
            "data_quality": event.data_quality,
            "description": desc,
            "event_datetime": event_when,
            "created_at": created_when,
            "feeder": feeder_label,
            "nominal_voltage_kv": event.nominal_voltage_kv,
            "nominal_frequency_hz": event.nominal_frequency_hz,
            "asset": asset_line,
            "relay": relay_line,
            "substation": substation or (ct0.station_name if ct0 else None),
            "bay": bay,
            "relay_tag": relay_tag or (ct0.recording_device if ct0 else None),
            "recording_device": ct0.recording_device if ct0 else None,
            "station_name": ct0.station_name if ct0 else None,
        },
        "cascade": {**cascade, "detected": bool(is_cascade)}
        if is_cascade or cascade
        else None,
        "multi_end": {**multi_end, "detected": bool(is_line)}
        if is_line or multi_end
        else None,
        "report_kind": report_kind,
        "files": file_inventory,
        "timing": timing,
        "operated_elements": operated_elements,
        "data_quality": dq,
        "electrical_analysis": {
            "limitations": limitations[:8]
            or ["Electrical quantities limited to validated COMTRADE channels."],
            "sample_rate_hz": sample_rate,
            "nominal_frequency_hz": event.nominal_frequency_hz,
            "rms": rms_summary,
        },
        "timeline": timeline_rows,
        "key_sequence": key_seq,
        "enrichment": enrich or None,
        "matrix": matrix_block or None,
        "compound_class": compound_class,
        "matrix_scenario": matrix_scenario,
        "matrix_traces": matrix_traces or None,
        "intertrip_summary": intertrip_label,
        "l2_causality": l2 or None,
        "protection_assessment": protection,
        "consistency_findings": [
            {
                "element": c.element,
                "status": c.status,
                "severity": c.severity,
                "explanation": c.explanation,
                "check_type": c.check_type,
                "check_label": _humanize_token(c.check_type),
            }
            for c in findings
        ],
        "fault_classification": fault_dict,
        "breaker_analysis": {
            "assessment": (
                "Breaker open evidenced"
                if timing.get("breaker_s") is not None or timing.get("interrupt_s") is not None
                else "INCONCLUSIVE"
            ),
            "reason": (
                "52a / current interruption present on timeline"
                if timing.get("breaker_s") is not None or timing.get("interrupt_s") is not None
                else "See timeline / protection digitals for breaker evidence"
            ),
            "pickup_to_trip_ms": timing.get("pickup_to_trip_ms"),
            "trip_to_clear_ms": timing.get("trip_to_clear_ms"),
        },
        "rca_hypotheses": {
            "hypotheses": hyp_rows,
            "primary": primary_hyp,
            "enrichment": enrich or {},
            "matrix": matrix_block or {},
            "compound_class": compound_class,
            "matrix_scenario": matrix_scenario,
        },
        "evidence": evidence_rows,
        "similar_events": {
            "message": "SIMILARITY RESULT: NOT AVAILABLE",
            "note": "Supporting evidence only — never treat as proof",
        },
        "decision": decision,
        "limitations": limitations,
        "setting_reference": setting_ref,
        "engineer_review": _format_engineer_review(latest_review),
        "generated_label": report_kind,
    }


def _normalize_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    """Ensure template-friendly shapes (distance display, pretty refs).

    Keep nested dicts as dicts — event_report.html.j2 reads
    ``data_quality.comtrade``, ``setting_reference.*``, and
    ``breaker_analysis.assessment``. Stringifying those fields made §3/§4
    render as NOT AVAILABLE / dashes even when DB data existed.
    """
    out = dict(analysis)
    fault = dict(out.get("fault_classification") or {})
    if fault:
        # Keep distance as dict for ReportGenerator.build_statements; expose display when present
        display = fault.get("distance_display")
        if not display:
            display = _format_fault_distance(fault)
        fault["distance_display"] = display  # may be None → template treats as N/A
        out["fault_classification"] = fault

    # If a prior path left these as JSON strings, parse back to dicts for Jinja
    for key in ("setting_reference", "data_quality", "breaker_analysis"):
        val = out.get(key)
        if isinstance(val, str) and val.strip().startswith("{"):
            try:
                parsed = json.loads(val)
            except (TypeError, ValueError, json.JSONDecodeError):
                parsed = None
            if isinstance(parsed, dict):
                out[key] = parsed

    elec = out.get("electrical_analysis")
    if isinstance(elec, dict):
        lims = elec.get("limitations")
        if isinstance(lims, list):
            elec = {
                **elec,
                "limitations": "; ".join(str(x) for x in lims) if lims else "None",
            }
            out["electrical_analysis"] = elec

    _pct_scores_in_rca(out.get("rca_hypotheses"))
    return out


def _build_sections(event: Event, analysis: dict[str, Any]) -> dict[str, Any]:
    """Compact sections payload for Report.sections JSON (plus full HTML separately)."""
    fault = analysis.get("fault_classification") or {}
    rca = analysis.get("rca_hypotheses") or {}
    return {
        "event": analysis.get("event") or {
            "id": event.id,
            "event_id": event.event_id,
            "status": event.status,
            "decision_state": event.decision_state,
        },
        "fault_classifications": [fault] if fault else [],
        "rca_hypotheses": rca.get("hypotheses") or [],
        "consistency": analysis.get("consistency_findings") or [],
        "decision": analysis.get("decision"),
        "has_timeline": bool(analysis.get("timeline")),
        "has_protection": bool(analysis.get("protection_assessment")),
        "has_evidence": bool(analysis.get("evidence")),
    }


def _render_html(analysis: dict[str, Any], title: str) -> str:
    # Always normalize scores to percent strings before Jinja (avoid filter mismatch)
    _pct_scores_in_rca(analysis.get("rca_hypotheses"))
    try:
        from reporting import ReportGenerator

        bundle = ReportGenerator().render(_normalize_analysis(analysis))
        html = bundle.html
        # Guard: never ship the stripped fallback look if Jinja returned empty
        if html and "Engineer Review" in html and "Executive Summary" in html:
            return html
        if html and "Event Identification" in html:
            return html
        # Some templates use different section numbering — accept rich HTML
        if html and len(html) > 3000 and "Jinja report fallback" not in html:
            return html
        raise RuntimeError("Jinja report HTML looked incomplete")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Jinja report render failed — retrying with safe context: %s", exc)
        try:
            from reporting import ReportGenerator

            safe = _normalize_analysis(analysis)
            _pct_scores_in_rca(safe.get("rca_hypotheses"))
            # Ensure score fields are plain strings (no reliance on Jinja filters)
            return ReportGenerator().render(safe).html
        except Exception as exc2:  # noqa: BLE001
            logger.exception("Jinja report fallback (%s)", exc2)
            fault = analysis.get("fault_classification") or {}
            hyps = (analysis.get("rca_hypotheses") or {}).get("hypotheses") or []
            findings = analysis.get("consistency_findings") or []
            lines = [
                f"<html><head><title>{title}</title></head><body>",
                f"<h1>{title}</h1>",
                "<h2>1. Executive Summary</h2>",
                f"<p>Event {(analysis.get('event') or {}).get('event_id')} — "
                f"decision={(analysis.get('decision') or {}).get('state') or 'NOT AVAILABLE'}</p>",
                "<h2>Fault</h2><ul>",
                (
                    f"<li>{fault.get('fault_type')} ({fault.get('status')})"
                    + (
                        f" · location={fault.get('distance_display')}"
                        if fault.get("distance_display")
                        else " · location=not applicable / not calculated"
                    )
                    + "</li>"
                ),
                "</ul><h2>Consistency</h2><ul>",
            ]
            from protection.ansi_names import format_ansi

            for c in findings:
                lines.append(
                    f"<li>{format_ansi(c.get('element'))} {c.get('check_type')}: {c.get('status')} "
                    f"[{c.get('severity')}]</li>"
                )
            lines.append("</ul><h2>RCA</h2><ul>")
            primary_h = next(
                (h for h in hyps if isinstance(h, dict) and h.get("is_primary")),
                hyps[0] if hyps else None,
            )
            if isinstance(primary_h, dict):
                score = primary_h.get("score")
                lines.append(
                    f"<li><b>Primary</b> [{primary_h.get('status')}] "
                    f"{primary_h.get('hypothesis_id') or primary_h.get('title')}: "
                    f"score {score}; {primary_h.get('statement') or ''}</li>"
                )
            er = analysis.get("engineer_review") or "PENDING"
            lines.append("</ul>")
            lines.append("<h2>19. Engineer Review</h2>")
            lines.append(f"<pre>{er}</pre>")
            lines.append(
                "<p><em>OBSERVED / CALCULATED / INFERRED / HYPOTHESIS statements "
                "are derived only from structured fields.</em></p></body></html>"
            )
            return "\n".join(lines)


def _pdf_esc(value: Any) -> str:
    text = "" if value is None else str(value)
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _pdf_dash(value: Any, fallback: str = "—") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def _pdf_humanize(value: Any) -> str:
    """Turn ENUM_STYLE tokens into compact readable labels for narrow PDF cells."""
    text = _pdf_dash(value)
    if text == "—":
        return text
    known = {
        "ANALYSIS_COMPLETE": "Analysis complete",
        "ANALYSIS_COMPLETE_WITH_WARNINGS": "Complete (warnings)",
        "ENGINEER_REVIEW_REQUIRED": "Review required",
        "DATA_INSUFFICIENT": "Data insufficient",
        "UNSUPPORTED_FORMAT": "Unsupported format",
        "INCONCLUSIVE": "Inconclusive",
        "UNLIKELY": "Unlikely",
        "PROBABLE": "Probable",
        "POSSIBLE": "Possible",
        "CONFIRMED": "Confirmed",
        "CONSISTENT": "Consistent",
        "INCONSISTENT": "Inconsistent",
        "ACCEPTABLE": "Acceptable",
        "NOT_VERIFIED": "Not verified",
        "NOT VERIFIED": "Not verified",
        "NOT_AVAILABLE": "Not available",
        "NOT AVAILABLE": "Not available",
        "UNKNOWN": "Unclassified",
    }
    if text in known:
        return known[text]
    upper = text.upper()
    if upper in known:
        return known[upper]
    if "_" in text and text.upper() == text:
        return text.replace("_", " ").title()
    return text


def _fault_type_display(fault: dict[str, Any]) -> str:
    """Technical fault-type label — avoid bare UNKNOWN."""
    ft = str(fault.get("fault_type") or "").strip().upper()
    ec = fault.get("event_class")
    if not ec:
        evc = (fault.get("evidence") or {}).get("event_classification")
        if isinstance(evc, dict):
            ec = evc.get("event_class")
        if not ec and isinstance(fault.get("features"), dict):
            ec = fault["features"].get("event_class")
    ec_u = str(ec or "").upper()
    if ec_u in ("ENERGIZATION", "MOTOR_START", "SWITCHING", "DISTURBANCE"):
        if ft in ("", "UNKNOWN", "INCONCLUSIVE"):
            return "N/A — non-fault event"
    if ft in ("", "UNKNOWN", "INCONCLUSIVE"):
        if ec_u == "FAULT":
            return "Unclassified (type indeterminate)"
        return "Unclassified"
    return str(fault.get("fault_type") or ft)


def _analysis_to_pdf(analysis: dict[str, Any], title: str) -> bytes:
    """Build a professional A4 PDF from the analysis payload (matches HTML report structure)."""
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    ink = colors.HexColor("#1e2a32")
    accent = colors.HexColor("#1f6f8b")
    muted = colors.HexColor("#5a6b7a")
    border_c = colors.HexColor("#d5dee6")
    panel = colors.HexColor("#f4f7fa")
    header_bg = colors.HexColor("#e8f0f5")
    ok = colors.HexColor("#0b7a45")
    warn = colors.HexColor("#9a6b00")
    bad = colors.HexColor("#a12828")
    white = colors.white
    stripe = colors.HexColor("#f7f9fb")

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle(
        "PdfH1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=accent,
        spaceAfter=2,
        spaceBefore=0,
        leading=20,
    )
    sub = ParagraphStyle(
        "PdfSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        textColor=muted,
        spaceAfter=8,
        leading=12,
    )
    h2 = ParagraphStyle(
        "PdfH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11,
        textColor=colors.HexColor("#234457"),
        spaceBefore=14,
        spaceAfter=4,
        leading=14,
    )
    h3 = ParagraphStyle(
        "PdfH3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=10,
        textColor=colors.HexColor("#345468"),
        spaceBefore=8,
        spaceAfter=3,
        leading=12,
    )
    body = ParagraphStyle(
        "PdfBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9,
        textColor=ink,
        leading=12,
        spaceAfter=4,
    )
    meta = ParagraphStyle(
        "PdfMeta",
        parent=body,
        fontSize=8.5,
        textColor=muted,
    )
    cell = ParagraphStyle(
        "PdfCell",
        parent=body,
        fontSize=8,
        leading=10,
        spaceAfter=0,
    )
    cell_label = ParagraphStyle(
        "PdfCellLabel",
        parent=cell,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#345468"),
    )
    kpi_lbl = ParagraphStyle(
        "PdfKpiLbl",
        parent=cell,
        fontSize=6.5,
        textColor=muted,
        alignment=TA_LEFT,
        spaceAfter=1,
        leading=8,
    )
    kpi_val = ParagraphStyle(
        "PdfKpiVal",
        parent=cell,
        fontName="Helvetica-Bold",
        fontSize=8,
        textColor=ink,
        alignment=TA_LEFT,
        leading=10,
        wordWrap="CJK",  # allow wrap inside narrow KPI cards
    )
    status_cell = ParagraphStyle(
        "PdfStatusCell",
        parent=cell,
        fontSize=7.5,
        leading=9.5,
    )

    page_w, _page_h = A4
    left_m = right_m = 14 * mm
    top_m = bottom_m = 16 * mm
    # Build doc early so widths match the real frame; zero frame padding to avoid overflow.
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title=title or "RCA Report",
        author="Protection Expert System",
        leftMargin=left_m,
        rightMargin=right_m,
        topMargin=top_m,
        bottomMargin=bottom_m,
    )
    for pt in doc.pageTemplates:
        for fr in pt.frames:
            fr.leftPadding = 0
            fr.rightPadding = 0
            fr.topPadding = 0
            fr.bottomPadding = 0
    usable = float(doc.width)
    cover_pad = 10.0
    accent_w = 3.5
    panel_w = usable - accent_w
    cover_inner = panel_w - (cover_pad * 2)

    def P(text: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(_pdf_esc(text), style)

    def section(story: list[Any], heading: str) -> None:
        story.append(Paragraph(_pdf_esc(heading), h2))
        story.append(
            HRFlowable(
                width="100%",
                thickness=1.6,
                color=accent,
                spaceBefore=0,
                spaceAfter=6,
            )
        )

    def _norm_widths(ratios: list[float], total: float) -> list[float]:
        s = sum(ratios) or 1.0
        return [total * (r / s) for r in ratios]

    def kv_table(rows: list[tuple[str, Any]]) -> Table:
        data = [
            [Paragraph(_pdf_esc(k), cell_label), Paragraph(_pdf_esc(_pdf_dash(v)), cell)]
            for k, v in rows
        ]
        tbl = Table(data, colWidths=_norm_widths([0.30, 0.70], usable), hAlign="LEFT")
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), panel),
                    ("BACKGROUND", (1, 0), (1, -1), white),
                    ("BOX", (0, 0), (-1, -1), 0.5, border_c),
                    ("INNERGRID", (0, 0), (-1, -1), 0.4, border_c),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return tbl

    def data_table(
        headers: list[str],
        rows: list[list[Any]],
        col_ratios: list[float] | None = None,
        *,
        humanize_cols: set[int] | None = None,
    ) -> Table:
        hum = humanize_cols or set()
        # Auto-humanize Status / Severity style columns by header name
        for i, h in enumerate(headers):
            if str(h).strip().lower() in {"status", "severity", "consistency", "decision"}:
                hum.add(i)
        head = [Paragraph(_pdf_esc(h), cell_label) for h in headers]
        body_rows: list[list[Any]] = []
        for row in rows:
            cells = []
            for i, c in enumerate(row):
                text = _pdf_humanize(c) if i in hum else _pdf_dash(c)
                style = status_cell if i in hum else cell
                cells.append(Paragraph(_pdf_esc(text), style))
            body_rows.append(cells)
        if not body_rows:
            body_rows = [[Paragraph("NOT AVAILABLE", cell)] + [Paragraph("", cell)] * (len(headers) - 1)]
        data = [head] + body_rows
        if col_ratios and len(col_ratios) == len(headers):
            widths = _norm_widths(col_ratios, usable)
        else:
            widths = [usable / len(headers)] * len(headers)
        tbl = Table(data, colWidths=widths, hAlign="LEFT", repeatRows=1)
        style_cmds: list[Any] = [
            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
            ("TEXTCOLOR", (0, 0), (-1, 0), accent),
            ("BOX", (0, 0), (-1, -1), 0.5, border_c),
            ("INNERGRID", (0, 0), (-1, -1), 0.35, border_c),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3.5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, stripe]),
        ]
        tbl.setStyle(TableStyle(style_cmds))
        return tbl

    def callout(paragraphs: list[str], *, html: bool = False) -> Table:
        # html=True: caller already escaped text and may include <b>/<font> markup
        bar_w = 3.0
        side_pad = 8.0
        content_w = usable - bar_w - (side_pad * 2)
        inner = [
            [Paragraph(p if html else _pdf_esc(p), body)]
            for p in paragraphs
            if p
        ]
        if not inner:
            inner = [[Paragraph("—", body)]]
        content = Table(inner, colWidths=[content_w])
        content.setStyle(
            TableStyle(
                [
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 1),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ]
            )
        )
        wrap = Table([["", content]], colWidths=[bar_w, usable - bar_w])
        wrap.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, 0), accent),
                    ("BACKGROUND", (1, 0), (1, 0), panel),
                    ("BOX", (0, 0), (-1, -1), 0.5, border_c),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (1, 0), (1, 0), side_pad),
                    ("RIGHTPADDING", (1, 0), (1, 0), side_pad),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (0, 0), 0),
                    ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ]
            )
        )
        return wrap

    def status_color(status: Any) -> colors.Color:
        s = str(status or "").upper()
        if s in ("CONFIRMED", "CONSISTENT", "OK", "ACCEPTABLE", "CLASSIFIED", "APPROVED"):
            return ok
        if s in ("PROBABLE", "POSSIBLE", "WARNING", "NOT VERIFIED", "PENDING", "UNVERIFIABLE"):
            return warn
        if s in ("INCONSISTENT", "REJECTED", "POOR", "INVALID", "UNLIKELY"):
            return bad
        return muted

    ev = analysis.get("event") if isinstance(analysis.get("event"), dict) else {}
    decision = analysis.get("decision") if isinstance(analysis.get("decision"), dict) else {}
    fault = analysis.get("fault_classification") if isinstance(analysis.get("fault_classification"), dict) else {}
    rca = analysis.get("rca_hypotheses") if isinstance(analysis.get("rca_hypotheses"), dict) else {}
    primary = rca.get("primary") if isinstance(rca.get("primary"), dict) else {}
    dq = analysis.get("data_quality") if isinstance(analysis.get("data_quality"), dict) else {}
    if isinstance(dq, str):
        try:
            dq = json.loads(dq)
        except (TypeError, ValueError, json.JSONDecodeError):
            dq = {}
    ct_list = dq.get("comtrade") if isinstance(dq.get("comtrade"), list) else []
    ct = ct_list[0] if ct_list else None
    settings = analysis.get("setting_reference") if isinstance(analysis.get("setting_reference"), dict) else {}
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except (TypeError, ValueError, json.JSONDecodeError):
            settings = {}
    timing = analysis.get("timing") if isinstance(analysis.get("timing"), dict) else {}
    breaker = analysis.get("breaker_analysis") if isinstance(analysis.get("breaker_analysis"), dict) else {}
    if isinstance(breaker, str):
        breaker = {"assessment": breaker}
    elec = analysis.get("electrical_analysis") if isinstance(analysis.get("electrical_analysis"), dict) else {}

    story: list[Any] = []

    # ——— Cover ———
    loc_parts = [ev.get("substation"), ev.get("bay"), ev.get("feeder")]
    loc = " · ".join(str(x) for x in loc_parts if x) or "NOT AVAILABLE"
    cover_rows = [
        [Paragraph("<b>Event</b>", cell_label), P(_pdf_dash(ev.get("event_id"), "NOT AVAILABLE"), cell)],
        [Paragraph("<b>DR time</b>", cell_label), P(_pdf_dash(ev.get("event_datetime"), "NOT AVAILABLE"), cell)],
        [Paragraph("<b>Created (app)</b>", cell_label), P(_pdf_dash(ev.get("created_at"), "—"), cell)],
        [Paragraph("<b>Location</b>", cell_label), P(loc, cell)],
        [
            Paragraph("<b>Relay / IED</b>", cell_label),
            P(_pdf_dash(ev.get("relay_tag") or ev.get("recording_device"), "NOT AVAILABLE"), cell),
        ],
    ]
    sys_bits = []
    if ev.get("nominal_voltage_kv") is not None:
        sys_bits.append(f"{ev.get('nominal_voltage_kv')} kV")
    freq = ev.get("nominal_frequency_hz") or elec.get("nominal_frequency_hz")
    if freq is not None:
        sys_bits.append(f"{freq} Hz")
    cover_rows.append(
        [Paragraph("<b>System</b>", cell_label), P(" · ".join(sys_bits) if sys_bits else "—", cell)]
    )
    cover_tbl = Table(cover_rows, colWidths=_norm_widths([0.24, 0.76], cover_inner))
    cover_tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), white),
                ("BOX", (0, 0), (-1, -1), 0.4, border_c),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, border_c),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    _ec = fault.get("event_class")
    if not _ec:
        _evc = (fault.get("evidence") or {}).get("event_classification")
        if isinstance(_evc, dict):
            _ec = _evc.get("event_class")
        if not _ec and isinstance(fault.get("features"), dict):
            _ec = fault["features"].get("event_class")
    kpi_items = [
        ("Event class", _pdf_humanize(_ec or "UNKNOWN")),
        ("Fault type", _fault_type_display(fault if isinstance(fault, dict) else {})),
        ("Decision", _pdf_humanize(decision.get("state") or ev.get("decision_state"))),
        (
            "Primary RCA",
            _pdf_humanize(primary.get("title") or primary.get("hypothesis_id") or "INCONCLUSIVE"),
        ),
    ]
    kpi_gap = 5.0
    kpi_col = (cover_inner - (kpi_gap * 3)) / 4.0
    kpi_cards = []
    for lbl, val in kpi_items:
        mini = Table(
            [
                [Paragraph(_pdf_esc(lbl).upper(), kpi_lbl)],
                [Paragraph(_pdf_esc(val), kpi_val)],
            ],
            colWidths=[kpi_col],
        )
        mini.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), white),
                    ("BOX", (0, 0), (-1, -1), 0.5, border_c),
                    ("LEFTPADDING", (0, 0), (-1, -1), 4),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        kpi_cards.append(mini)
    kpi_row = Table(
        [[kpi_cards[0], "", kpi_cards[1], "", kpi_cards[2], "", kpi_cards[3]]],
        colWidths=[kpi_col, kpi_gap, kpi_col, kpi_gap, kpi_col, kpi_gap, kpi_col],
    )
    kpi_row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    cover_block = Table(
        [
            [Paragraph(_pdf_esc(title or "Protection Disturbance Analysis Report"), h1)],
            [Paragraph("Deterministic engineering report · COMTRADE / DR analysis", sub)],
            [cover_tbl],
            [Spacer(1, 6)],
            [kpi_row],
        ],
        colWidths=[cover_inner],
    )
    cover_block.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    cover_shell = Table(
        [["", cover_block]],
        colWidths=[accent_w, panel_w],
    )
    cover_shell.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, 0), accent),
                ("BACKGROUND", (1, 0), (1, 0), panel),
                ("BOX", (0, 0), (-1, -1), 0.6, border_c),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (0, 0), 0),
                ("RIGHTPADDING", (0, 0), (0, 0), 0),
                ("LEFTPADDING", (1, 0), (1, 0), cover_pad),
                ("RIGHTPADDING", (1, 0), (1, 0), cover_pad),
                ("TOPPADDING", (0, 0), (-1, -1), cover_pad),
                ("BOTTOMPADDING", (0, 0), (-1, -1), cover_pad),
            ]
        )
    )
    story.append(cover_shell)
    story.append(Spacer(1, 10))

    # ——— 1. Executive summary ———
    section(story, "1. Executive Summary")
    prim_title = primary.get("title") or "Root cause not confirmed"
    prim_status = primary.get("status") or ""
    score = primary.get("score")
    score_txt = f" (score {score})" if score not in (None, "") else ""

    def _hex(c: colors.Color) -> str:
        return f"{int(c.red * 255):02x}{int(c.green * 255):02x}{int(c.blue * 255):02x}"

    summary_lines = [
        f"<b>{_pdf_esc(prim_title)}</b>"
        + (
            f" — <font color='#{_hex(status_color(prim_status))}'><b>{_pdf_esc(prim_status)}</b></font>"
            if prim_status
            else ""
        )
        + _pdf_esc(score_txt)
    ]
    if primary.get("statement"):
        summary_lines.append(str(primary["statement"]))
    _ec_sum = fault.get("event_class")
    if not _ec_sum:
        _evc_sum = (fault.get("evidence") or {}).get("event_classification")
        if isinstance(_evc_sum, dict):
            _ec_sum = _evc_sum.get("event_class")
        if not _ec_sum and isinstance(fault.get("features"), dict):
            _ec_sum = fault["features"].get("event_class")
    meta_bits = [
        f"Event class: <b>{_pdf_esc(_pdf_dash(_ec_sum, 'UNKNOWN'))}</b>",
        f"Fault: <b>{_pdf_esc(_fault_type_display(fault if isinstance(fault, dict) else {}))}</b> "
        f"({_pdf_esc(_pdf_dash(fault.get('status')))}, {_pdf_esc(_pdf_dash(fault.get('confidence'), 'INCONCLUSIVE'))})",
    ]
    from protection.ansi_names import format_ansi_list

    ops = analysis.get("operated_elements") or []
    if ops:
        ops_named = format_ansi_list([str(x) for x in ops]) or ", ".join(str(x) for x in ops)
        meta_bits.append(f"Operated: <b>{_pdf_esc(ops_named)}</b>")
    if timing.get("pickup_to_trip_ms") is not None:
        meta_bits.append(f"Pickup→trip: <b>{_pdf_esc(timing['pickup_to_trip_ms'])} ms</b>")
    if timing.get("trip_to_clear_ms") is not None:
        meta_bits.append(f"Trip→clear: <b>{_pdf_esc(timing['trip_to_clear_ms'])} ms</b>")
    dist = fault.get("distance_display")
    if dist and "NOT_APPLICABLE" not in str(dist).upper() and "NOT APPLICABLE" not in str(dist).upper():
        meta_bits.append(f"Location: <b>{_pdf_esc(dist)}</b>")
    if analysis.get("intertrip_summary") and analysis["intertrip_summary"] != "None asserted":
        meta_bits.append(f"Intertrip: <b>{_pdf_esc(analysis['intertrip_summary'])}</b>")
    summary_lines.append(" · ".join(meta_bits))
    story.append(callout(summary_lines, html=True))
    story.append(Spacer(1, 4))

    # ——— 2. Event identification ———
    section(story, "2. Event Identification")
    story.append(
        kv_table(
            [
                ("Event ID", ev.get("event_id")),
                ("DR time (relay)", ev.get("event_datetime")),
                ("Created in app", ev.get("created_at")),
                ("Description", ev.get("description")),
                ("Substation", ev.get("substation") or ev.get("station_name")),
                ("Bay", ev.get("bay")),
                ("Feeder / circuit", ev.get("feeder")),
                (
                    "Nominal voltage",
                    f"{ev['nominal_voltage_kv']} kV" if ev.get("nominal_voltage_kv") is not None else None,
                ),
                ("Relay / IED tag", ev.get("relay_tag")),
                ("Recording device", ev.get("recording_device")),
                ("Event status", ev.get("status")),
            ]
        )
    )

    # ——— 3. COMTRADE quality ———
    section(story, "3. COMTRADE Record Quality")
    if isinstance(ct, dict) and ct:
        story.append(
            kv_table(
                [
                    ("Station (CFG)", ct.get("station_name")),
                    ("Recording device", ct.get("recording_device")),
                    ("Record start", ct.get("start_timestamp")),
                    (
                        "Sample rate",
                        f"{ct['sample_rate_hz']} Hz" if ct.get("sample_rate_hz") is not None else None,
                    ),
                    ("Samples", ct.get("total_samples")),
                    (
                        "Analog / digital channels",
                        f"{_pdf_dash(ct.get('analog_channel_count'))} / {_pdf_dash(ct.get('digital_channel_count'))}",
                    ),
                    ("Validation", ct.get("validation_status")),
                    ("Data quality", ct.get("data_quality") or dq.get("event_data_quality")),
                    ("Parse warnings", ct.get("parse_warnings")),
                ]
            )
        )
    elif dq.get("event_data_quality") and str(dq.get("event_data_quality")) != "NOT AVAILABLE":
        story.append(
            kv_table(
                [
                    ("Data quality", dq.get("event_data_quality")),
                    (
                        "COMTRADE detail",
                        "Record-level CFG metadata not loaded — open COMTRADE tab or re-run analysis.",
                    ),
                ]
            )
        )
    else:
        story.append(P(dq.get("status") or "NOT AVAILABLE — re-run analysis after COMTRADE parse.", meta))

    # ——— 4. Settings ———
    section(story, "4. Setting Reference (bound for this analysis)")
    if settings.get("status"):
        hint = settings.get("hint")
        story.append(P(f"{settings['status']}" + (f" — {hint}" if hint else ""), meta))
    else:
        story.append(
            kv_table(
                [
                    ("Source", settings.get("setting_source_used")),
                    ("Version", settings.get("setting_version")),
                    ("Setting group", settings.get("setting_group")),
                    ("Active group", settings.get("active_setting_group_verification")),
                    ("Approval", settings.get("setting_approval")),
                    ("Settings file", settings.get("setting_file")),
                    ("Parameters loaded", settings.get("param_count")),
                ]
            )
        )
        if settings.get("explanation"):
            story.append(P(settings["explanation"], meta))

    # ——— 5. Sequence ———
    section(story, "5. Sequence of Operation")
    seq_meta = []
    if timing.get("pickup_to_trip_ms") is not None:
        seq_meta.append(f"Pickup → trip: <b>{_pdf_esc(timing['pickup_to_trip_ms'])} ms</b>")
    if timing.get("trip_to_clear_ms") is not None:
        seq_meta.append(f"Trip → current clear: <b>{_pdf_esc(timing['trip_to_clear_ms'])} ms</b>")
    if breaker.get("assessment"):
        seq_meta.append(f"Breaker: <b>{_pdf_esc(breaker['assessment'])}</b>")
    if seq_meta:
        story.append(Paragraph(" · ".join(seq_meta), meta))
    seq_src = analysis.get("key_sequence") or analysis.get("timeline") or []
    if analysis.get("key_sequence"):
        story.append(
            P(
                f"Key operate sequence ({len(analysis['key_sequence'])} of "
                f"{len(analysis.get('timeline') or [])} timeline events).",
                meta,
            )
        )
    tl_rows = []
    for e in seq_src:
        if not isinstance(e, dict):
            continue
        ts = e.get("timestamp")
        try:
            ts_s = f"{float(ts):.4f}" if ts is not None else "—"
        except (TypeError, ValueError):
            ts_s = _pdf_dash(ts)
        step = e.get("event_type_label") or _humanize_event_type(e.get("event_type")) or "—"
        src = str(e.get("source") or "—")
        # Prefer channel name from analog:/digital: source in the step when useful
        if src.startswith("analog:") or src.startswith("digital:"):
            ch = src.split(":", 1)[1]
            if ch and ch not in str(step):
                step = f"{step} ({ch})"
        val = e.get("value")
        if not val or val == "—":
            val = _timeline_value_display(e, src)
        tl_rows.append([step, ts_s, val, src, e.get("confidence")])
    story.append(
        data_table(
            ["Step", "Time (s)", "Value", "Source", "Confidence"],
            tl_rows,
            [0.30, 0.12, 0.18, 0.24, 0.16],
        )
    )

    # ——— 6. Electrical ———
    section(story, "6. Electrical Quantities")
    elec_meta = []
    if elec.get("sample_rate_hz") is not None:
        elec_meta.append(f"Sample rate: {elec['sample_rate_hz']} Hz")
    if elec.get("nominal_frequency_hz") is not None:
        elec_meta.append(f"Nominal frequency: {elec['nominal_frequency_hz']} Hz")
    if elec_meta:
        story.append(P(" · ".join(elec_meta), meta))
    rms = elec.get("rms") if isinstance(elec.get("rms"), dict) else {}
    if rms:
        rms_rows = []
        for name, row in rms.items():
            if not isinstance(row, dict):
                row = {"value": row}
            val = row.get("value")
            try:
                val_s = f"{float(val):.3f}" if val is not None else "—"
            except (TypeError, ValueError):
                val_s = _pdf_dash(val)
            rms_rows.append([name, val_s, row.get("unit"), row.get("status")])
        story.append(data_table(["Channel", "RMS", "Unit", "Status"], rms_rows, [0.35, 0.25, 0.15, 0.25]))
    else:
        story.append(P("RMS summary NOT AVAILABLE — open Waveforms / Electrical after analysis.", meta))

    # ——— 7. Fault ———
    section(story, "7. Fault Classification & Location")
    _ec_sec = fault.get("event_class")
    _evc_sec = (fault.get("evidence") or {}).get("event_classification")
    if not isinstance(_evc_sec, dict):
        _evc_sec = {}
    if not _ec_sec:
        _ec_sec = _evc_sec.get("event_class")
        if not _ec_sec and isinstance(fault.get("features"), dict):
            _ec_sec = fault["features"].get("event_class")
    _dur_ev = _evc_sec.get("evidence") if isinstance(_evc_sec.get("evidence"), dict) else {}
    if not _dur_ev and isinstance(fault.get("features"), dict):
        _feat_ec = fault["features"].get("event_classification")
        if isinstance(_feat_ec, dict) and isinstance(_feat_ec.get("evidence"), dict):
            _dur_ev = _feat_ec["evidence"]
    _dur_ms = _dur_ev.get("duration_ms")
    _dur_band = _dur_ev.get("duration_band")
    _dur_txt = "—"
    if _dur_ms is not None:
        _dur_txt = f"{_dur_ms} ms"
        if _dur_band:
            _dur_txt += f" ({_dur_band})"
        if _dur_ev.get("cleared") is True:
            _dur_txt += "; cleared"
        elif _dur_ev.get("cleared") is False:
            _dur_txt += "; not cleared in DR"
    story.append(
        kv_table(
            [
                ("DFR event class", _ec_sec or "UNKNOWN"),
                ("Event class status", fault.get("event_class_status") or "—"),
                ("Event duration", _dur_txt),
                ("Fault type", _fault_type_display(fault if isinstance(fault, dict) else {})),
                ("Classification status", fault.get("status")),
                ("Confidence", fault.get("confidence") or "INCONCLUSIVE"),
                (
                    "Fault location",
                    fault.get("distance_display")
                    or "Not applicable / not calculated for this scheme",
                ),
            ]
        )
    )
    flims = fault.get("limitations")
    if isinstance(flims, list) and flims:
        story.append(P("Notes: " + "; ".join(str(x) for x in flims), meta))

    # ——— 8. Protection ———
    section(story, "8. Protection Performance")
    story.append(
        P(
            "Actual: TRIPPED = trip digital asserted; PICKED UP = start/pickup only "
            "(not a trip). UNVERIFIABLE = no verified settings to judge expected operate.",
            meta,
        )
    )
    from protection.ansi_names import format_ansi

    prot_rows = []
    for a in analysis.get("protection_assessment") or []:
        if not isinstance(a, dict):
            continue
        if str(a.get("element") or "").upper() == "GENERAL":
            continue
        prot_rows.append(
            [
                format_ansi(a.get("element")),
                a.get("enabled_display") or a.get("enabled"),
                a.get("pickup_display") or a.get("pickup"),
                a.get("trip_display") or a.get("trip"),
                a.get("expected_operation"),
                a.get("actual_operation"),
                a.get("consistency"),
            ]
        )
    story.append(
        data_table(
            ["Element", "Enabled", "Pickup", "Trip", "Expected", "Actual", "Consistency"],
            prot_rows,
            [0.14, 0.11, 0.13, 0.13, 0.14, 0.14, 0.21],
        )
    )

    # ——— 9. Consistency ———
    section(story, "9. Protection Consistency Check")
    cons_rows = []
    for f in analysis.get("consistency_findings") or []:
        if not isinstance(f, dict):
            continue
        cons_rows.append(
            [
                format_ansi(f.get("element")),
                f.get("check_label") or f.get("check_type"),
                f.get("status"),
                f.get("severity"),
                f.get("explanation"),
            ]
        )
    story.append(
        data_table(
            ["Element", "Check", "Status", "Severity", "Explanation"],
            cons_rows,
            [0.14, 0.20, 0.16, 0.12, 0.38],
        )
    )

    # ——— 10. RCA ———
    section(story, "10. Root Cause Assessment")
    if primary:
        rca_lines = [
            f"<b>Primary:</b> {_pdf_esc(primary.get('title') or primary.get('hypothesis_id'))} — "
            f"<font color='#{_hex(status_color(primary.get('status')))}'><b>{_pdf_esc(primary.get('status'))}</b></font>"
            f" · score {_pdf_esc(_pdf_dash(primary.get('score')))}"
        ]
        if primary.get("statement"):
            rca_lines.append(str(primary["statement"]))
        if primary.get("explanation"):
            rca_lines.append(str(primary["explanation"]))
        chain = primary.get("causal_chain") or []
        if chain:
            rca_lines.append(
                "<b>Causal chain:</b> "
                + _pdf_esc(" → ".join(str(x) for x in chain[:8]))
            )
        support = primary.get("supporting_evidence_labels") or primary.get("supporting_evidence") or []
        missing = primary.get("missing_evidence_labels") or primary.get("missing_evidence") or []
        if support:
            rca_lines.append("<b>Supporting evidence:</b> " + _pdf_esc("; ".join(str(x) for x in support)))
        rca_lines.append(
            "<b>Missing evidence:</b> "
            + (_pdf_esc("; ".join(str(x) for x in missing)) if missing else "none recorded")
        )
        story.append(callout(rca_lines, html=True))
    else:
        story.append(P("INCONCLUSIVE — no primary hypothesis ranked.", meta))

    # ——— 11. Actions ———
    section(story, "11. Recommended Verification")
    actions = decision.get("recommended_actions") or primary.get("recommended_actions") or [
        "Verify active setting group against the event time",
        "Review Consistency and Protection tables",
        "Confirm channel mapping and DR targets",
    ]
    for a in actions:
        story.append(P(f"• {_pdf_dash(a)}", body))

    # ——— 12. Limitations ———
    section(story, "12. Limitations & Confidence")
    story.append(
        Paragraph(
            f"Overall confidence: <b>{_pdf_esc(_pdf_dash(decision.get('confidence'), 'INCONCLUSIVE'))}</b>",
            body,
        )
    )
    lims = analysis.get("limitations") or []
    if not lims:
        lims = ["None recorded"]
    for lim in lims:
        story.append(P(f"• {_pdf_dash(lim)}", body))

    # ——— 13. Review ———
    section(story, "13. Engineer Review")
    er = analysis.get("engineer_review")
    if isinstance(er, dict):
        story.append(P(er.get("action") or "PENDING", body))
        if er.get("reviewed_at"):
            story.append(P(f"Reviewed at: {er['reviewed_at']}", meta))
        if er.get("decision_state"):
            story.append(P(f"Decision state: {er['decision_state']}", meta))
        if er.get("comments"):
            story.append(P(f"Comments: {er['comments']}", meta))
    elif er:
        for er_line in str(er).splitlines() or [str(er)]:
            if er_line.strip():
                story.append(P(er_line, body))
    else:
        story.append(
            P(
                "PENDING — complete Review (ACCEPT / MODIFY / REJECT / …) after engineering check.",
                meta,
            )
        )

    # ——— 14. Files ———
    section(story, "14. Evidence Files")
    files = analysis.get("files") or []
    if files:
        file_rows = [
            [f.get("filename"), f.get("type"), f.get("sha256")]
            for f in files
            if isinstance(f, dict)
        ]
        story.append(
            data_table(
                ["Filename", "Type", "SHA-256 (prefix)"],
                file_rows,
                [0.45, 0.20, 0.35],
            )
        )
    else:
        story.append(P("No file inventory available.", meta))

    story.append(Spacer(1, 12))
    story.append(
        HRFlowable(width="100%", thickness=0.5, color=border_c, spaceBefore=4, spaceAfter=6)
    )
    story.append(
        P(
            "Report generated from structured analysis artefacts only. "
            "Conclusions distinguish OBSERVED / CALCULATED / INFERRED / HYPOTHESIS. "
            "This system does not invent measurements, settings, or root cause, "
            "and does not issue OT control commands.",
            meta,
        )
    )

    event_label = _pdf_dash(ev.get("event_id"), "Event")
    doc.title = title or f"RCA Report — {event_label}"

    def _on_page(canvas_obj: Any, _doc: Any) -> None:
        canvas_obj.saveState()
        # Use RGB floats — avoids ReportLab/Python 3.14 Color eval quirks in callbacks
        canvas_obj.setStrokeColorRGB(0.835, 0.871, 0.902)  # #d5dee6
        canvas_obj.setLineWidth(0.5)
        y_top = A4[1] - 12 * mm
        canvas_obj.line(left_m, y_top, page_w - right_m, y_top)
        canvas_obj.setFont("Helvetica", 7.5)
        canvas_obj.setFillColorRGB(0.353, 0.420, 0.478)  # #5a6b7a
        canvas_obj.drawString(left_m, A4[1] - 10 * mm, "Protection Disturbance Analysis Report")
        canvas_obj.drawRightString(page_w - right_m, A4[1] - 10 * mm, str(event_label))
        canvas_obj.line(left_m, 12 * mm, page_w - right_m, 12 * mm)
        canvas_obj.drawCentredString(
            page_w / 2,
            8 * mm,
            f"Page {_doc.page} · Read-only analysis · No invented measurements",
        )
        canvas_obj.restoreState()

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buf.getvalue()


def _html_to_pdf(html: str, title: str) -> bytes:
    """Legacy HTML scrape fallback — prefer ``_analysis_to_pdf`` for professional layout."""
    import re
    from html import unescape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    body = html
    body = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", body)
    body = re.sub(r"(?is)<style\b[^>]*>.*?</style>", "", body)
    body = re.sub(r"(?is)<head\b[^>]*>.*?</head>", "", body)
    body = re.sub(r"(?is)<!DOCTYPE[^>]*>", "", body)
    body = re.sub(r"(?is)</?html\b[^>]*>", "", body)
    body = re.sub(r"(?is)</?body\b[^>]*>", "", body)

    def _clean_inline(fragment: str) -> str:
        t = fragment or ""
        t = re.sub(r"(?is)<br\s*/?>", "[[BR]]", t)
        t = re.sub(r"(?is)</?(span|strong|b|em|i)\b[^>]*>", "", t)
        t = re.sub(r"(?is)<[^>]+>", "", t)
        t = unescape(t)
        return (
            t.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("[[BR]]", "<br/>")
            .strip()
        )

    styles = getSampleStyleSheet()
    accent = colors.HexColor("#1f6f8b")
    h1 = ParagraphStyle(
        "FbH1", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=14, textColor=accent, spaceAfter=8,
    )
    h2 = ParagraphStyle(
        "FbH2", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=11, textColor=accent, spaceBefore=10, spaceAfter=4,
    )
    body_style = ParagraphStyle(
        "FbBody", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=9, leading=12, spaceAfter=3,
    )
    cell_style = ParagraphStyle(
        "FbCell", parent=body_style, fontSize=8, leading=10, spaceAfter=0,
    )
    story: list[Any] = [
        Paragraph(_clean_inline(title) or "Protection Disturbance Event Report", h1),
        HRFlowable(width="100%", thickness=1.5, color=accent, spaceAfter=8),
    ]
    pattern = re.compile(r"(?is)<(h1|h2|p|ul|ol|table|div)(\s[^>]*)?>(.*?)</\1>")
    for m in pattern.finditer(body):
        tag, inner = m.group(1).lower(), m.group(3)
        if tag in ("h1", "h2"):
            story.append(Paragraph(_clean_inline(inner), h1 if tag == "h1" else h2))
        elif tag == "p":
            t = _clean_inline(inner)
            if t:
                story.append(Paragraph(t, body_style))
        elif tag in ("ul", "ol"):
            for li in re.findall(r"(?is)<li\b[^>]*>(.*?)</li>", inner):
                t = _clean_inline(li)
                if t:
                    story.append(Paragraph(f"• {t}", body_style))
        elif tag == "table":
            data = []
            for rh in re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>", inner):
                cells = re.findall(r"(?is)<t[hd]\b[^>]*>(.*?)</t[hd]>", rh)
                if cells:
                    data.append([Paragraph(_clean_inline(c) or "—", cell_style) for c in cells])
            if data:
                n = max(len(r) for r in data)
                for r in data:
                    while len(r) < n:
                        r.append(Paragraph("", cell_style))
                w = (A4[0] - 36 * 2) / n
                tbl = Table(data, colWidths=[w] * n)
                tbl.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8f0f5")),
                            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d5dee6")),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(tbl)
                story.append(Spacer(1, 6))
        elif tag == "div":
            t = _clean_inline(inner)
            if t:
                story.append(Paragraph(t, body_style))

    buf = io.BytesIO()
    SimpleDocTemplate(
        buf, pagesize=A4, title=title,
        leftMargin=16 * mm, rightMargin=16 * mm, topMargin=14 * mm, bottomMargin=14 * mm,
    ).build(story)
    return buf.getvalue()


async def _load_analysis_payload(db: AsyncSession, event: Event) -> dict[str, Any]:
    """Always rebuild from DB rows (source of truth), then merge richer snapshot fields."""
    # Refresh event.extra in case plant labels / settings were updated after load
    await db.refresh(event)

    faults = (
        await db.execute(
            select(FaultClassification).where(FaultClassification.event_id == event.id)
        )
    ).scalars().all()
    hyps = (
        await db.execute(
            select(RcaHypothesis)
            .where(RcaHypothesis.event_id == event.id)
            .order_by(RcaHypothesis.rank)
        )
    ).scalars().all()
    findings = (
        await db.execute(
            select(ConsistencyFinding).where(ConsistencyFinding.event_id == event.id)
        )
    ).scalars().all()
    timeline = (
        await db.execute(
            select(EventTimeline)
            .where(EventTimeline.event_id == event.id)
            .order_by(EventTimeline.sequence)
        )
    ).scalars().all()
    ops = (
        await db.execute(
            select(ProtectionOperation).where(ProtectionOperation.event_id == event.id)
        )
    ).scalars().all()
    evidence = (
        await db.execute(select(Evidence).where(Evidence.event_id == event.id))
    ).scalars().all()
    comtrades = (
        await db.execute(select(ComtradeFile).where(ComtradeFile.event_id == event.id))
    ).scalars().all()
    files = (
        await db.execute(select(EventFile).where(EventFile.event_id == event.id))
    ).scalars().all()
    measurements = (
        await db.execute(select(Measurement).where(Measurement.event_id == event.id))
    ).scalars().all()
    latest_review = (
        await db.execute(
            select(EngineerReview)
            .where(EngineerReview.event_id == event.id)
            .order_by(EngineerReview.reviewed_at.desc())
            .limit(1)
        )
    ).scalars().first()

    analysis = _rebuild_analysis_from_db(
        event,
        faults=list(faults),
        hyps=list(hyps),
        findings=list(findings),
        timeline=list(timeline),
        ops=list(ops),
        evidence=list(evidence),
        comtrades=list(comtrades),
        files=list(files),
        measurements=list(measurements),
        latest_review=latest_review,
    )

    # Overlay snapshot only where it adds non-empty richer content
    extra = event.extra if isinstance(event.extra, dict) else {}
    # Prefer DB review; fall back to persisted disposition on the event
    if analysis.get("engineer_review") in (None, "", "PENDING"):
        latest_meta = extra.get("latest_engineer_review")
        if isinstance(latest_meta, dict) and latest_meta.get("action"):
            lines = [str(latest_meta["action"]).strip().upper()]
            if latest_meta.get("reviewed_at"):
                lines.append(f"Reviewed at: {latest_meta['reviewed_at']}")
            if latest_meta.get("decision_state"):
                lines.append(f"Decision state: {latest_meta['decision_state']}")
            if latest_meta.get("comments"):
                lines.append(f"Comments: {latest_meta['comments']}")
            analysis["engineer_review"] = "\n".join(lines)
        else:
            snap_er = None
            if isinstance(extra.get("report_analysis"), dict):
                snap_er = extra["report_analysis"].get("engineer_review")
            if isinstance(snap_er, str) and snap_er.strip() and snap_er.strip().upper() != "PENDING":
                analysis["engineer_review"] = snap_er

    snapshot = extra.get("report_analysis")
    if isinstance(snapshot, dict):
        for key in (
            "electrical_analysis",
            "breaker_analysis",
            "similar_events",
            "decision",
            "setting_reference",
            "rca_hypotheses",
            "enrichment",
            "matrix",
        ):
            snap_val = snapshot.get(key)
            cur = analysis.get(key)
            if not snap_val:
                continue
            if key == "electrical_analysis" and isinstance(snap_val, dict):
                merged = dict(cur or {})
                if snap_val.get("rms"):
                    merged["rms"] = {**(merged.get("rms") or {}), **snap_val["rms"]}
                if snap_val.get("limitations"):
                    merged["limitations"] = snap_val["limitations"]
                if snap_val.get("sample_rate_hz"):
                    merged["sample_rate_hz"] = snap_val["sample_rate_hz"]
                analysis[key] = merged
            elif key == "rca_hypotheses" and isinstance(snap_val, dict):
                if snap_val.get("hypotheses") and (
                    not cur or not (cur.get("hypotheses") if isinstance(cur, dict) else None)
                ):
                    analysis[key] = snap_val
                elif isinstance(cur, dict) and snap_val.get("primary") and not cur.get("primary"):
                    analysis[key] = {**cur, "primary": snap_val["primary"]}
                # Ensure scores display as percentages even when snapshot is used
                _pct_scores_in_rca(analysis.get("rca_hypotheses"))
            elif key in ("enrichment", "matrix") and isinstance(snap_val, dict):
                if not cur:
                    analysis[key] = snap_val
                elif isinstance(cur, dict):
                    analysis[key] = {**snap_val, **cur}
            elif key == "setting_reference" and isinstance(snap_val, dict):
                if any(v not in (None, "", []) for v in snap_val.values()):
                    # Prefer snapshot when it has real values; keep DB rebuild if snapshot empty
                    if not any(
                        v not in (None, "", [])
                        for v in (cur or {}).values()
                        if isinstance(cur, dict)
                    ):
                        analysis[key] = snap_val
            elif not cur:
                analysis[key] = snap_val

        # Prefer longer timeline / protection lists from either side
        for key in ("timeline", "protection_assessment", "consistency_findings", "evidence"):
            snap_list = snapshot.get(key) or []
            cur_list = analysis.get(key) or []
            if isinstance(snap_list, list) and len(snap_list) > len(cur_list):
                analysis[key] = snap_list

        # Refresh derived summary fields from merged enrichment / timeline
        enrich = analysis.get("enrichment") if isinstance(analysis.get("enrichment"), dict) else {}
        matrix_block = analysis.get("matrix") if isinstance(analysis.get("matrix"), dict) else {}
        casc = analysis.get("cascade") if isinstance(analysis.get("cascade"), dict) else {}
        if not analysis.get("compound_class"):
            analysis["compound_class"] = (
                enrich.get("compound_class")
                or matrix_block.get("compound_class")
                or casc.get("compound_class")
            )
        if not analysis.get("matrix_scenario"):
            analysis["matrix_scenario"] = (
                enrich.get("matrix_scenario")
                or matrix_block.get("matched_scenario_id")
                or casc.get("matrix_scenario")
            )
        if not analysis.get("matrix_traces"):
            analysis["matrix_traces"] = list(
                enrich.get("matrix_traces")
                or matrix_block.get("traces")
                or casc.get("matrix_traces")
                or []
            )[:16] or None
        tl = analysis.get("timeline") if isinstance(analysis.get("timeline"), list) else []
        # Rebuild key sequence when timeline rows are dicts with event_type
        if tl and isinstance(tl[0], dict) and "event_type" in tl[0]:
            analysis["key_sequence"] = _key_sequence_rows(tl)
            analysis["intertrip_summary"] = _intertrip_summary(tl, enrich)
        deep = enrich.get("ladder_deep") if isinstance(enrich.get("ladder_deep"), dict) else {}
        if isinstance(deep.get("l2_causality"), dict):
            analysis["l2_causality"] = deep["l2_causality"]

    _pct_scores_in_rca(analysis.get("rca_hypotheses"))
    return analysis


async def generate_report(
    db: AsyncSession,
    event: Event,
    *,
    report_type: str = "RCA",
    title: Optional[str] = None,
    fmt: str = "JSON",
    generated_by: Optional[str] = None,
    request_id: Optional[str] = None,
) -> Report:
    settings = get_settings()
    analysis = await _load_analysis_payload(db, event)
    sections = _build_sections(event, analysis)
    hyp_count = len((analysis.get("rca_hypotheses") or {}).get("hypotheses") or [])
    find_count = len(analysis.get("consistency_findings") or [])
    primary = (analysis.get("rca_hypotheses") or {}).get("primary") or {}
    fault = analysis.get("fault_classification") or {}
    prim_title = primary.get("title") or primary.get("hypothesis_id") or "INCONCLUSIVE"
    prim_status = primary.get("status") or ""
    ft = fault.get("fault_type") or "UNKNOWN"
    ec = fault.get("event_class") or "UNKNOWN"
    summary_bits = [
        f"{prim_title}" + (f" ({prim_status})" if prim_status else ""),
        f"event class {ec}",
        f"fault {ft}",
    ]
    if analysis.get("intertrip_summary") and analysis["intertrip_summary"] != "None asserted":
        summary_bits.append(f"intertrip {analysis['intertrip_summary']}")
    summary = (
        f"{event.event_id}: " + " · ".join(summary_bits)
        + f" · {hyp_count} hypotheses, {find_count} consistency findings, "
        f"{len(analysis.get('key_sequence') or analysis.get('timeline') or [])} key sequence steps."
    )
    report_title = title or f"RCA Report — {event.event_id}"
    fmt_u = (fmt or "JSON").upper()
    storage_key = None
    html = None

    if fmt_u in ("HTML", "PDF", "JSON"):
        html = _render_html(analysis, report_title)
        storage = StorageService()
        # Full HTML for UI preview (not truncated)
        sections = {**sections, "html_content": html}
        if fmt_u == "HTML":
            raw = html.encode("utf-8")
            sha = hashlib.sha256(raw).hexdigest()
            storage_key = storage.put_bytes(
                raw, sha256=sha, prefix=f"reports/{event.id}", suffix=".html",
                content_type="text/html",
            )
        elif fmt_u == "PDF":
            try:
                try:
                    pdf = _analysis_to_pdf(analysis, report_title)
                except Exception:  # noqa: BLE001
                    logger.exception("Structured PDF failed — falling back to HTML scrape")
                    pdf = _html_to_pdf(html, report_title)
                sha = hashlib.sha256(pdf).hexdigest()
                storage_key = storage.put_bytes(
                    pdf, sha256=sha, prefix=f"reports/{event.id}", suffix=".pdf",
                    content_type="application/pdf",
                )
            except Exception as exc:  # noqa: BLE001
                logger.exception("PDF generation failed")
                fmt_u = "HTML"
                raw = html.encode("utf-8")
                sha = hashlib.sha256(raw).hexdigest()
                storage_key = storage.put_bytes(
                    raw, sha256=sha, prefix=f"reports/{event.id}", suffix=".html"
                )
                sections = {
                    **sections,
                    "pdf_error": str(exc),
                    "html_content": html,
                }
        else:
            raw = html.encode("utf-8")
            sha = hashlib.sha256(raw).hexdigest()
            storage_key = storage.put_bytes(
                raw, sha256=sha, prefix=f"reports/{event.id}", suffix=".html"
            )

    report = Report(
        event_id=event.id,
        report_type=report_type,
        title=report_title,
        status="READY",
        template_version=settings.report_template_version,
        format=fmt_u,
        summary=summary,
        sections=sections,
        storage_key=storage_key,
        generated_by=generated_by,
        generated_at=datetime.now(timezone.utc),
    )
    db.add(report)
    await db.flush()
    await write_audit(
        db,
        action="EXPORT",
        user_id=generated_by,
        object_type="Report",
        object_id=report.id,
        new_value={"event_id": event.id, "format": fmt_u, "storage_key": storage_key},
        request_id=request_id,
    )
    return report


async def list_reports(db: AsyncSession, event_id: str) -> list[Report]:
    result = await db.execute(
        select(Report)
        .where(Report.event_id == event_id)
        .order_by(Report.created_at.desc())
    )
    return list(result.scalars().all())


async def get_report(db: AsyncSession, report_id: str) -> Optional[Report]:
    result = await db.execute(select(Report).where(Report.id == report_id))
    return result.scalar_one_or_none()


async def get_report_bytes(db: AsyncSession, report_id: str) -> tuple[bytes, str, str]:
    """Return (payload, media_type, filename) for download."""
    report = await get_report(db, report_id)
    if report is None:
        raise FileNotFoundError(report_id)
    if not report.storage_key:
        raw = (report.summary or "").encode("utf-8")
        return raw, "text/plain", f"{report.id}.txt"
    storage = StorageService()
    data = storage.get_bytes(report.storage_key)
    if (report.format or "").upper() == "PDF":
        return data, "application/pdf", f"{report.event_id}.pdf"
    return data, "text/html", f"{report.event_id}.html"
