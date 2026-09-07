"""Report generation — JSON + Jinja HTML + PDF packaging."""

from __future__ import annotations

import hashlib
import io
import json
import logging
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
    dist = fault.get("distance")
    if isinstance(dist, dict):
        if dist.get("value_km") is not None:
            unit = dist.get("unit") or "km"
            method = dist.get("method") or ""
            suffix = f" ({method})" if method else ""
            return f"{dist['value_km']} {unit}{suffix}"
        # Explicit attempt failed → NOT CALCULABLE; silent / N/A → omit from report
        status = str(dist.get("status") or "").upper()
        if status in ("NOT_APPLICABLE", "N/A", "NA"):
            return None
        if status in ("NOT_CALCULABLE", "INCONCLUSIVE") or dist.get("reason"):
            reason = dist.get("reason") or "insufficient validated inputs"
            return f"FAULT DISTANCE: NOT CALCULABLE — {reason}"
        return None
    if fault.get("distance_km") is not None:
        return f"{fault['distance_km']} km"
    if isinstance(dist, (int, float)):
        return f"{dist} km"
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
    if not desc and files:
        names = ", ".join(f.original_filename for f in files[:8])
        more = f" (+{len(files) - 8} more)" if len(files) > 8 else ""
        desc = f"Upload batch — {names}{more}"

    primary_fault = next((f for f in faults if f.is_primary), faults[0] if faults else None)
    fault_dict: dict[str, Any] = {}
    if primary_fault is not None:
        feat = primary_fault.features if isinstance(primary_fault.features, dict) else {}
        dist_detail = feat.get("distance_detail") if isinstance(feat.get("distance_detail"), dict) else {}
        distance_applicable = feat.get("distance_applicable")
        if distance_applicable is None:
            distance_applicable = str(dist_detail.get("status") or "").upper() not in (
                "NOT_APPLICABLE",
                "N/A",
                "NA",
            ) and bool(
                primary_fault.distance_km is not None
                or primary_fault.location_method
                or (dist_detail.get("algorithms") and dist_detail.get("status") != "NOT_APPLICABLE")
            )
        else:
            distance_applicable = bool(distance_applicable)
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
        if primary_fault.distance_km is not None:
            dist_status = "OK"
        elif not distance_applicable:
            dist_status = "NOT_APPLICABLE"
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
        fault_dict = {
            "fault_type": primary_fault.fault_type,
            "status": primary_fault.status,
            "confidence": primary_fault.confidence_level or _conf_label(primary_fault.confidence),
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

    # Fill gaps from consistency findings so every checked element appears
    for f in findings:
        el = str(f.element or "UNKNOWN")
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
    protection = [{k: v for k, v in r.items() if k != "_op"} for r in by_el.values()]

    timeline_rows = []
    for te in sorted(timeline, key=lambda x: (x.sequence or 0, x.t_us or 0)):
        payload = te.payload if isinstance(te.payload, dict) else {}
        ts = payload.get("timestamp")
        if ts is None and te.t_us is not None:
            ts = te.t_us / 1_000_000.0
        timeline_rows.append(
            {
                "event_type": te.event_type,
                "timestamp": float(ts) if ts is not None else 0.0,
                "source": te.source or payload.get("source") or "COMTRADE",
                "confidence": te.confidence
                if isinstance(te.confidence, str)
                else _conf_label(te.confidence)
                if te.confidence is not None
                else payload.get("confidence") or "INCONCLUSIVE",
                "label": te.label,
            }
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
        row = {
            "hypothesis_id": h.hypothesis_code or h.title,
            "title": h.title,
            "status": h.status,
            "score": _format_score_pct(h.confidence),
            "score_raw": h.confidence,
            "confidence": h.confidence_level or _conf_label(h.confidence),
            "statement": h.statement,
            "missing_evidence": missing or [],
            "supporting_evidence": h.supporting_evidence_ids or [],
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

    dq: dict[str, Any] = {}
    if event.data_quality:
        dq["event_data_quality"] = event.data_quality
    for cf in comtrades[:3]:
        dq.setdefault("comtrade", [])
        if isinstance(dq["comtrade"], list):
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
                }
            )
    if not dq:
        dq = {"status": "NOT AVAILABLE — re-run analysis after COMTRADE parse"}

    setting_ref = {
        "setting_source_used": extra.get("setting_source"),
        "setting_version": extra.get("setting_version"),
        "setting_group": extra.get("setting_group"),
        "active_setting_group_verification": extra.get("active_group_status"),
        "setting_approval": extra.get("setting_approval"),
        "setting_file": extra.get("setting_file"),
        "param_count": extra.get("setting_param_count"),
        "explanation": extra.get("settings_file_verification_note"),
    }
    if not any(v is not None and v != "" for v in setting_ref.values()):
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
    # Drop legacy Z1 / FAULT DISTANCE noise when distance is out of scope
    if primary_fault is not None:
        feat = primary_fault.features if isinstance(primary_fault.features, dict) else {}
        dist_ok = bool(feat.get("distance_applicable")) or primary_fault.distance_km is not None
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

    return {
        "event": {
            "id": event.id,
            "event_id": event.event_id,
            "status": event.status,
            "decision_state": event.decision_state,
            "data_quality": event.data_quality,
            "description": desc,
            "feeder": event.feeder,
            "nominal_voltage_kv": event.nominal_voltage_kv,
            "nominal_frequency_hz": event.nominal_frequency_hz,
            "asset": asset_line,
            "relay": relay_line,
            "substation": (extra.get("plant_labels") or {}).get("substation_name")
            if isinstance(extra.get("plant_labels"), dict)
            else extra.get("substation_name"),
            "bay": (extra.get("plant_labels") or {}).get("bay_name")
            if isinstance(extra.get("plant_labels"), dict)
            else extra.get("bay_name"),
        },
        "data_quality": dq,
        "electrical_analysis": {
            "limitations": limitations[:8]
            or ["Electrical quantities limited to validated COMTRADE channels."],
            "sample_rate_hz": sample_rate,
            "nominal_frequency_hz": event.nominal_frequency_hz,
            "rms": rms_summary,
        },
        "timeline": timeline_rows,
        "protection_assessment": protection,
        "consistency_findings": [
            {
                "element": c.element,
                "status": c.status,
                "severity": c.severity,
                "explanation": c.explanation,
                "check_type": c.check_type,
            }
            for c in findings
        ],
        "fault_classification": fault_dict,
        "breaker_analysis": {
            "assessment": "INCONCLUSIVE",
            "reason": "See timeline / protection digitals for breaker evidence",
        },
        "rca_hypotheses": {
            "hypotheses": hyp_rows,
            "primary": primary_hyp,
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
    }


def _normalize_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
    """Ensure template-friendly shapes (distance display, pretty refs)."""
    out = dict(analysis)
    fault = dict(out.get("fault_classification") or {})
    if fault:
        # Keep distance as dict for ReportGenerator.build_statements; expose display when present
        display = fault.get("distance_display")
        if not display:
            display = _format_fault_distance(fault)
        fault["distance_display"] = display  # may be None → template treats as N/A
        out["fault_classification"] = fault

    sr = out.get("setting_reference")
    if isinstance(sr, dict):
        out["setting_reference"] = json.dumps(sr, indent=2, default=str)
    dq = out.get("data_quality")
    if isinstance(dq, dict):
        out["data_quality"] = json.dumps(dq, indent=2, default=str)

    elec = out.get("electrical_analysis")
    if isinstance(elec, dict):
        lims = elec.get("limitations")
        if isinstance(lims, list):
            elec = {
                **elec,
                "limitations": "; ".join(str(x) for x in lims) if lims else "None",
            }
            out["electrical_analysis"] = elec

    ba = out.get("breaker_analysis")
    if isinstance(ba, dict):
        out["breaker_analysis"] = (
            f"{ba.get('assessment', 'INCONCLUSIVE')}"
            + (f" — {ba['reason']}" if ba.get("reason") else "")
        )
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
        if html and "19. Engineer Review" in html:
            return html
        if html and "<h2>1. Event Identification</h2>" in html:
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
            for c in findings:
                lines.append(
                    f"<li>{c.get('element')} {c.get('check_type')}: {c.get('status')} "
                    f"[{c.get('severity')}]</li>"
                )
            lines.append("</ul><h2>RCA</h2><ul>")
            for h in hyps:
                score = h.get("score")
                lines.append(
                    f"<li>[{h.get('status')}] {h.get('hypothesis_id') or h.get('title')}: "
                    f"score {score}; {h.get('statement') or ''}</li>"
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


def _html_to_pdf(html: str, title: str) -> bytes:
    """Convert report HTML to PDF with headings, lists, and tables (no CSS dump)."""
    import re
    from html import unescape

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        Preformatted,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    # Drop head/style/script so CSS never appears as body text
    body = html
    body = re.sub(r"(?is)<script\b[^>]*>.*?</script>", "", body)
    body = re.sub(r"(?is)<style\b[^>]*>.*?</style>", "", body)
    body = re.sub(r"(?is)<head\b[^>]*>.*?</head>", "", body)
    body = re.sub(r"(?is)<!DOCTYPE[^>]*>", "", body)
    body = re.sub(r"(?is)</?html\b[^>]*>", "", body)
    body = re.sub(r"(?is)</?body\b[^>]*>", "", body)
    body = re.sub(r"(?is)<meta\b[^>]*/?>", "", body)
    body = re.sub(r"(?is)<title\b[^>]*>.*?</title>", "", body)

    def _clean_inline(fragment: str) -> str:
        t = fragment or ""
        t = re.sub(r"(?is)<br\s*/?>", "[[BR]]", t)
        t = re.sub(r"(?is)</?span\b[^>]*>", "", t)
        t = re.sub(r"(?is)<strong\b[^>]*>", "[[B]]", t)
        t = re.sub(r"(?is)</strong>", "[[/B]]", t)
        t = re.sub(r"(?is)<b\b[^>]*>", "[[B]]", t)
        t = re.sub(r"(?is)</b>", "[[/B]]", t)
        t = re.sub(r"(?is)<em\b[^>]*>", "[[I]]", t)
        t = re.sub(r"(?is)</em>", "[[/I]]", t)
        t = re.sub(r"(?is)<i\b[^>]*>", "[[I]]", t)
        t = re.sub(r"(?is)</i>", "[[/I]]", t)
        t = re.sub(r"(?is)<[^>]+>", "", t)
        t = unescape(t)
        t = (
            t.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        t = (
            t.replace("[[BR]]", "<br/>")
            .replace("[[B]]", "<b>")
            .replace("[[/B]]", "</b>")
            .replace("[[I]]", "<i>")
            .replace("[[/I]]", "</i>")
        )
        return t.strip()

    def _plain(fragment: str) -> str:
        return unescape(re.sub(r"(?is)<[^>]+>", "", fragment)).strip()

    styles = getSampleStyleSheet()
    navy = colors.HexColor("#1f4f68")
    muted = colors.HexColor("#5a6e7e")
    border = colors.HexColor("#b8c5d4")
    header_bg = colors.HexColor("#e4ecf2")

    h1 = ParagraphStyle(
        "ReportH1",
        parent=styles["Heading1"],
        fontName="Times-Bold",
        fontSize=16,
        textColor=navy,
        spaceAfter=8,
        spaceBefore=4,
        leading=20,
    )
    h2 = ParagraphStyle(
        "ReportH2",
        parent=styles["Heading2"],
        fontName="Times-Bold",
        fontSize=12,
        textColor=navy,
        spaceBefore=12,
        spaceAfter=6,
        leading=15,
        borderPadding=2,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName="Times-Roman",
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1a1a1a"),
        spaceAfter=4,
    )
    meta_style = ParagraphStyle(
        "ReportMeta",
        parent=body_style,
        textColor=muted,
        fontSize=9,
    )
    cell_style = ParagraphStyle(
        "ReportCell",
        parent=body_style,
        fontSize=8,
        leading=10,
        spaceAfter=0,
    )
    pre_style = ParagraphStyle(
        "ReportPre",
        parent=body_style,
        fontName="Courier",
        fontSize=8,
        leading=10,
        backColor=colors.HexColor("#f4f6f8"),
        leftIndent=4,
        rightIndent=4,
    )

    story: list[Any] = []
    story.append(Paragraph(_clean_inline(title) or "Protection Disturbance Event Report", h1))
    story.append(
        HRFlowable(width="100%", thickness=1, color=navy, spaceBefore=2, spaceAfter=10)
    )

    # Walk top-level block tags in order
    pattern = re.compile(
        r"(?is)<(h1|h2|p|ul|ol|pre|table|div)(\s[^>]*)?>(.*?)</\1>"
    )
    pos = 0
    for m in pattern.finditer(body):
        # Ignore orphan text between blocks (usually whitespace)
        tag = m.group(1).lower()
        inner = m.group(3)

        if tag == "h1":
            story.append(Paragraph(_clean_inline(inner), h1))
            story.append(
                HRFlowable(width="100%", thickness=0.6, color=border, spaceBefore=0, spaceAfter=6)
            )
        elif tag == "h2":
            story.append(Paragraph(_clean_inline(inner), h2))
            story.append(
                HRFlowable(width="100%", thickness=0.5, color=border, spaceBefore=0, spaceAfter=4)
            )
        elif tag == "p":
            cls = m.group(2) or ""
            style = meta_style if "meta" in cls.lower() else body_style
            text = _clean_inline(inner)
            if text:
                story.append(Paragraph(text, style))
        elif tag in ("ul", "ol"):
            items = re.findall(r"(?is)<li\b[^>]*>(.*?)</li>", inner)
            for li in items:
                text = _clean_inline(li)
                if text:
                    story.append(Paragraph(f"• {text}", body_style))
            story.append(Spacer(1, 4))
        elif tag == "pre":
            plain = _plain(inner)
            if plain:
                # Preformatted avoids Paragraph XML issues with braces/JSON
                story.append(Preformatted(plain, pre_style, maxLineLength=95))
                story.append(Spacer(1, 6))
        elif tag == "table":
            rows_html = re.findall(r"(?is)<tr\b[^>]*>(.*?)</tr>", inner)
            data: list[list[Any]] = []
            for rh in rows_html:
                cells = re.findall(r"(?is)<t[hd]\b[^>]*>(.*?)</t[hd]>", rh)
                if not cells:
                    continue
                data.append(
                    [Paragraph(_clean_inline(c) or "—", cell_style) for c in cells]
                )
            if data:
                col_count = max(len(r) for r in data)
                for r in data:
                    while len(r) < col_count:
                        r.append(Paragraph("", cell_style))
                usable = A4[0] - 36 - 36
                col_w = usable / col_count
                tbl = Table(data, colWidths=[col_w] * col_count, hAlign="LEFT")
                tbl.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), header_bg),
                            ("TEXTCOLOR", (0, 0), (-1, 0), navy),
                            ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
                            ("FONTSIZE", (0, 0), (-1, -1), 8),
                            ("GRID", (0, 0), (-1, -1), 0.4, border),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                            ("TOPPADDING", (0, 0), (-1, -1), 3),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                            (
                                "ROWBACKGROUNDS",
                                (0, 1),
                                (-1, -1),
                                [colors.white, colors.HexColor("#f7f9fb")],
                            ),
                        ]
                    )
                )
                story.append(tbl)
                story.append(Spacer(1, 8))
        elif tag == "div":
            # Flatten nested paragraphs / lists inside divs (e.g. limitations)
            nested = list(pattern.finditer(inner))
            if nested:
                for nm in nested:
                    ntag = nm.group(1).lower()
                    ninner = nm.group(3)
                    if ntag in ("p",):
                        t = _clean_inline(ninner)
                        if t:
                            story.append(Paragraph(t, body_style))
                    elif ntag in ("ul", "ol"):
                        for li in re.findall(r"(?is)<li\b[^>]*>(.*?)</li>", ninner):
                            t = _clean_inline(li)
                            if t:
                                story.append(Paragraph(f"• {t}", body_style))
                    elif ntag == "pre":
                        plain = _plain(ninner)
                        if plain:
                            story.append(Preformatted(plain, pre_style, maxLineLength=95))
            else:
                t = _clean_inline(inner)
                if t:
                    story.append(Paragraph(t, body_style))
        pos = m.end()

    if len(story) <= 2:
        # Fallback: plain text without tags/CSS
        plain = _plain(body)
        for line in plain.splitlines():
            line = line.strip()
            if line:
                story.append(Paragraph(line.replace("&", "&amp;"), body_style))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        title=title,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )
    doc.build(story)
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
    summary = (
        f"RCA report for event {event.event_id}: "
        f"{hyp_count} hypotheses, {find_count} consistency findings, "
        f"{len(analysis.get('timeline') or [])} timeline events, "
        f"{len(analysis.get('protection_assessment') or [])} protection assessments."
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
