"""Persist full AnalysisPipeline results into ORM tables for UI tabs."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import (
    ConsistencyFinding,
    Event,
    EventFile,
    EventTimeline,
    Evidence,
    FaultClassification,
    Measurement,
    ProtectionOperation,
    RcaHypothesis,
)
from app.services.storage import StorageService
from app.services.waveform_service import _materialize_event_files
from app.services.settings_package import load_relay_settings_from_files

logger = logging.getLogger(__name__)

_CONF_MAP = {
    "HIGH": 0.85,
    "MEDIUM": 0.6,
    "LOW": 0.35,
    "INCONCLUSIVE": 0.15,
}


def _json_safe(obj: Any) -> Any:
    """Make values safe for SQLAlchemy JSON columns (no datetime/bytes/custom)."""
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (bytes, bytearray)):
        return obj.decode("utf-8", errors="replace")
    try:
        json.dumps(obj)
        return obj
    except (TypeError, ValueError):
        return str(obj)


def _conf_float(level: Any) -> float:
    if isinstance(level, (int, float)):
        return float(level)
    return float(_CONF_MAP.get(str(level or "").upper(), 0.2))


_CHECK_LABELS = {
    "enabled_vs_pickup": "Enabled vs pickup",
    "enabled_vs_trip": "Enabled vs trip",
    "pickup_vs_trip": "Pickup vs trip",
    "timing": "Operating time vs setting",
    "direction": "Directionality",
    "reach": "Reach / zone",
}


def _humanize_evidence(ev: dict[str, Any]) -> tuple[str, str, str, str]:
    """Return (title, summary, polarity, evidence_key) for UI-friendly evidence rows."""
    param = str(ev.get("parameter") or ev.get("title") or "evidence")
    interp = str(ev.get("interpretation") or ev.get("summary") or "").strip()
    source = str(ev.get("source_type") or "").upper()
    key = str(ev.get("evidence_id") or param)[:64]

    if param.startswith("rms:"):
        ch = param.split(":", 1)[1]
        title = f"Measured RMS - channel {ch}"
        unit = str(ev.get("unit") or "")
        val = ev.get("value")
        summary = interp or (
            f"Value {val} {unit}".strip() if val is not None else "RMS sample from COMTRADE"
        )
        polarity = "SUPPORTING" if "status=ok" in interp.lower() or not interp else "NEUTRAL"
        return title, summary, polarity, key

    label = _CHECK_LABELS.get(param, param.replace("_", " ").title())
    if source == "PROTECTION_RULE":
        title = f"Consistency check - {label}"
    else:
        title = label

    expected = ev.get("expected")
    observed = ev.get("observed")
    parts: list[str] = []
    if interp:
        parts.append(interp)
    if expected is not None or observed is not None:
        parts.append(f"Expected: {expected} · Observed: {observed}")
    summary = " | ".join(parts) if parts else "Supporting calculation / rule output"

    low = summary.lower()
    if "inconsistent" in low or "conflict" in low:
        polarity = "CONTRADICTING"
    elif "cannot verify" in low or "incomplete" in low or "not available" in low:
        polarity = "MISSING"
    elif "consistent" in low or "status=ok" in low:
        polarity = "SUPPORTING"
    else:
        polarity = "NEUTRAL"
    return title, summary, polarity, key


async def persist_engineering_analysis(
    db: AsyncSession,
    event: Event,
    *,
    force: bool = False,
) -> dict[str, Any]:
    """
    Re-parse COMTRADE, run AnalysisPipeline, and write results used by Overview
    and every analysis tab. Does not invent measurements or settings.
    """
    settings = get_settings()
    storage = StorageService()
    files = (
        await db.execute(select(EventFile).where(EventFile.event_id == event.id))
    ).scalars().all()
    if not files:
        return {"success": False, "error": "No uploaded files"}

    # Skip if already engineered unless force
    if not force:
        existing_fault = (
            await db.execute(
                select(FaultClassification).where(
                    FaultClassification.event_id == event.id,
                    FaultClassification.fault_type != "UNKNOWN",
                )
            )
        ).scalars().first()
        if existing_fault is not None:
            return {"success": True, "skipped": True, "reason": "already engineered"}

    paths = _materialize_event_files(storage, list(files))
    if not paths:
        return {"success": False, "error": "No COMTRADE cfg/dat/cff among uploads"}

    from comtrade.service import ComtradeService
    from app.services.analysis_pipeline import AnalysisPipeline

    ingest = ComtradeService().ingest(paths, validate_after_parse=True)
    if not ingest.success or ingest.record is None:
        return {
            "success": False,
            "error": ingest.error or "COMTRADE ingest failed",
        }

    record = ingest.record
    relay_settings, setting_candidates = load_relay_settings_from_files(
        storage, list(files)
    )
    meta = relay_settings.get("_meta") if isinstance(relay_settings.get("_meta"), dict) else {}

    # Merge vendor settings previously saved via settings-ingest API into analysis inputs
    extra_pre = event.extra if isinstance(event.extra, dict) else {}
    if not setting_candidates and isinstance(extra_pre.get("relay_settings"), dict):
        from app.services.settings_ingest import setting_records_from_ingested

        synthetic = {
            "vendor": (extra_pre.get("settings_ingest") or {}).get("vendor") or "GENERIC",
            "filename": (extra_pre.get("settings_ingest") or {}).get("filename") or "event.extra",
            "mapped": {
                "protection": extra_pre.get("relay_settings") or {},
                "line": extra_pre.get("line_params") or {},
                "ct_vt": extra_pre.get("ct_vt") or {},
            },
            "status": "OK",
        }
        flat_extra, recs_extra = setting_records_from_ingested(synthetic)
        if recs_extra:
            relay_settings = {**flat_extra, **relay_settings}
            setting_candidates = recs_extra
            meta = relay_settings.get("_meta") if isinstance(relay_settings.get("_meta"), dict) else meta

    # RIO / XRIO trip-zone geometry for R–X (after settings merge so scalar fallback works)
    rio_texts: list[tuple[str, str]] = []
    for ef in files:
        name = ef.original_filename or ""
        low = name.lower()
        if not (low.endswith((".rio", ".xrio", ".xml")) or "rio" in low):
            continue
        try:
            raw = storage.get_bytes(ef.storage_key)
            rio_texts.append((name, raw.decode("utf-8", errors="replace")))
        except Exception:  # noqa: BLE001
            continue
    from settings.rio_zones import extract_distance_zones

    distance_zones = extract_distance_zones(
        file_texts=rio_texts,
        relay_settings=relay_settings if isinstance(relay_settings, dict) else None,
    )

    from app.services.side_files import (
        load_side_timeline_from_files,
    )

    line_params: dict[str, Any] = {}
    ct_vt_ratios: dict[str, Any] = {}
    # Prefer engineer/vendor-ingest line & CT/VT already on the event
    if isinstance(extra_pre.get("line_params"), dict):
        line_params = dict(extra_pre["line_params"])
    if isinstance(extra_pre.get("ct_vt"), dict):
        ct_vt_ratios = dict(extra_pre["ct_vt"])
    param_detected_keys: dict[str, str] = {}
    # Prefer files tagged SETTINGS / named *setting* / *relay*, then any JSON with ratios
    json_files = [ef for ef in files if (ef.original_filename or "").lower().endswith(".json")]
    preferred = [
        ef
        for ef in json_files
        if ef.source_type == "SETTINGS"
        or "setting" in (ef.original_filename or "").lower()
        or "relay" in (ef.original_filename or "").lower()
    ]
    from app.services.param_detect import detect_plant_parameters

    for ef in preferred + [ef for ef in json_files if ef not in preferred]:
        try:
            data = json.loads(storage.get_bytes(ef.storage_key).decode("utf-8"))
            if isinstance(data, dict):
                det = detect_plant_parameters(data)
                lp = det.get("line") or {}
                cv = det.get("ct_vt") or {}
                keys = det.get("detected_keys") or {}
                if lp and not line_params:
                    line_params = lp
                elif lp:
                    for k, v in lp.items():
                        line_params.setdefault(k, v)
                if cv and not ct_vt_ratios:
                    ct_vt_ratios = cv
                elif cv:
                    for k, v in cv.items():
                        ct_vt_ratios.setdefault(k, v)
                if keys:
                    param_detected_keys.update({k: v for k, v in keys.items() if k not in param_detected_keys})
                if line_params and ct_vt_ratios:
                    break
        except Exception:  # noqa: BLE001
            continue

    # Also detect plant params from flat keys on vendor-ingest / text settings
    if (not line_params or not ct_vt_ratios) and relay_settings:
        det = detect_plant_parameters(relay_settings)
        if not line_params:
            line_params = det.get("line") or {}
        if not ct_vt_ratios:
            ct_vt_ratios = det.get("ct_vt") or {}
        param_detected_keys.update(det.get("detected_keys") or {})

    extra_timeline, side_summary = load_side_timeline_from_files(storage, list(files))

    # Enrich plant labels from CFG when wizard left UNKNOWN
    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    plant = extra.get("plant_labels") if isinstance(extra.get("plant_labels"), dict) else {}
    current_ss = str(plant.get("substation_name") or extra.get("substation_name") or "").upper()
    current_relay = str(plant.get("relay_tag") or extra.get("relay_tag") or "").upper()
    if record.station and current_ss in ("", "UNKNOWN"):
        extra["substation_name"] = record.station
        plant["substation_name"] = record.station
    if record.device and current_relay in ("", "NOT VERIFIED"):
        extra["relay_tag"] = record.device
        plant["relay_tag"] = record.device

    for ef in files:
        n = (ef.original_filename or "").lower()
        if not n.endswith(".json"):
            continue
        try:
            data = json.loads(storage.get_bytes(ef.storage_key).decode("utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(data, dict):
            continue
        asset = data.get("asset") if isinstance(data.get("asset"), dict) else {}
        if asset.get("substation") and current_ss in ("", "UNKNOWN"):
            extra["substation_name"] = asset["substation"]
            plant["substation_name"] = asset["substation"]
            current_ss = str(asset["substation"]).upper()
        if asset.get("bay") and str(plant.get("bay_name") or "").upper() in ("", "NOT VERIFIED"):
            plant["bay_name"] = asset["bay"]
            extra["bay_name"] = asset["bay"]
        if asset.get("feeder") and not event.feeder:
            event.feeder = str(asset["feeder"])
        if asset.get("nominal_voltage_kv") and not event.nominal_voltage_kv:
            try:
                event.nominal_voltage_kv = float(asset["nominal_voltage_kv"])
            except (TypeError, ValueError):
                pass
        # Do not break — scan all JSON packages for plant / voltage fields

    # Fill nominal voltage from settings / VT / filename / station when missing
    if not event.nominal_voltage_kv:
        from app.services.param_detect import extract_nominal_voltage_kv

        json_blobs: list[Any] = []
        texts: list[str] = []
        filenames = [ef.original_filename or "" for ef in files]
        for ef in files:
            name = (ef.original_filename or "").lower()
            try:
                raw = storage.get_bytes(ef.storage_key)
            except Exception:  # noqa: BLE001
                continue
            if name.endswith(".json"):
                try:
                    data = json.loads(raw.decode("utf-8"))
                    if isinstance(data, dict):
                        json_blobs.append(data)
                except Exception:  # noqa: BLE001
                    pass
            elif name.endswith((".txt", ".csv", ".cfg", ".set", ".rio", ".xrio", ".xml")):
                texts.append(raw.decode("utf-8", errors="replace")[:20000])
        station = (
            record.station
            or plant.get("substation_name")
            or extra.get("substation_name")
            or ""
        )
        kv, kv_src = extract_nominal_voltage_kv(
            json_blobs=json_blobs,
            texts=texts,
            filenames=filenames,
            station=str(station) if station else None,
        )
        if kv is not None:
            event.nominal_voltage_kv = kv
            extra["nominal_voltage_source"] = kv_src

    if plant:
        extra["plant_labels"] = plant

    # Asset registry → cause enrichment (e.g. CABLE → cable_asset_confirmed)
    if event.asset_id and not extra.get("asset_type"):
        from app.models import Asset

        asset_row = await db.get(Asset, event.asset_id)
        if asset_row is not None:
            extra["asset_type"] = asset_row.asset_type
            extra["asset_name"] = asset_row.name or asset_row.asset_tag

    if setting_candidates:
        from app.core.config import get_settings as _gs
        from app.services.settings_package import apply_upload_auto_approval

        meta = apply_upload_auto_approval(meta if isinstance(meta, dict) else {})
        auto = bool(_gs().auto_approve_uploaded_settings)
        extra["setting_source"] = str(
            meta.get("source")
            or relay_settings.get("setting_source")
            or "APPROVED_RELAY_BASE"
        )
        extra["setting_version"] = str(
            meta.get("version")
            or relay_settings.get("setting_version")
            or "UPLOADED"
        )
        extra["setting_group"] = str(
            meta.get("group") or relay_settings.get("setting_group") or "Base"
        )
        file_verified = bool(meta.get("verified"))
        engineer_verified = bool(extra.get("engineer_verified_active_group"))
        engineer_approved = bool(extra.get("settings_engineer_approved")) or str(
            extra.get("setting_approval") or ""
        ).upper() == "APPROVED"
        if auto:
            engineer_approved = True
            engineer_verified = True
            extra["settings_engineer_approved"] = True
            extra["engineer_verified_active_group"] = True
            extra["settings_approval_note"] = (
                extra.get("settings_approval_note")
                or "Auto-approved on upload (auto_approve_uploaded_settings)"
            )
        verified = file_verified or engineer_verified or engineer_approved or auto
        if verified:
            for rec in setting_candidates:
                try:
                    rec.verified = True
                    if engineer_approved or auto:
                        rec.approval_status = "APPROVED"
                except Exception:  # noqa: BLE001
                    pass
        extra["active_group_status"] = "VERIFIED" if verified else "NOT VERIFIED"
        if engineer_approved or auto:
            extra["setting_approval"] = "APPROVED"
        else:
            extra["setting_approval"] = str(
                meta.get("approval_status")
                or relay_settings.get("approval_status")
                or "NOT VERIFIED"
            )
        if meta.get("verification_note"):
            extra["settings_file_verification_note"] = meta["verification_note"]
        if relay_settings.get("_source_file"):
            extra["setting_file"] = relay_settings["_source_file"]
        extra["setting_param_count"] = len(setting_candidates)
    extra["file_processing"] = {
        "comtrade": "OK" if record.samples else "NO_SAMPLES",
        "settings": (
            f"{relay_settings.get('_source_file')} ({len(setting_candidates)} params)"
            if setting_candidates
            else "NOT LOADED"
        ),
        "soe": side_summary.get("soe") or "NOT LOADED",
        "event_report": side_summary.get("event_report") or "NOT LOADED",
        "line_params": "OK" if line_params else "NOT LOADED",
        "ct_vt": "OK" if ct_vt_ratios else "NOT LOADED",
        "param_keys_detected": param_detected_keys or None,
    }
    event.extra = _json_safe(extra)

    plant_ss = (
        plant.get("substation_name")
        or extra.get("substation_name")
        or record.station
        or None
    )
    plant_bay = plant.get("bay_name") or extra.get("bay_name") or None
    plant_relay = (
        plant.get("relay_tag") or extra.get("relay_tag") or record.device or None
    )
    asset_line = ", ".join(
        p
        for p in (
            f"Substation: {plant_ss}" if plant_ss else None,
            f"Bay: {plant_bay}" if plant_bay else None,
            f"Feeder: {event.feeder}" if event.feeder else None,
            (
                f"Nominal voltage: {event.nominal_voltage_kv} kV"
                if event.nominal_voltage_kv is not None
                else None
            ),
        )
        if p
    )
    relay_line = ", ".join(
        p
        for p in (
            f"Relay tag: {plant_relay}" if plant_relay else None,
            f"Recording device: {record.device}" if record.device else None,
        )
        if p
    )
    pipeline = AnalysisPipeline()
    extra_ev = event.extra if isinstance(event.extra, dict) else {}
    result = pipeline.run(
        record,
        event_meta={
            "event_id": event.event_id,
            "description": event.description
            or f"Upload batch — {len(files)} file(s)",
            "substation": plant_ss,
            "bay": plant_bay,
            "feeder": event.feeder,
            "nominal_voltage_kv": event.nominal_voltage_kv,
            "asset": asset_line or None,
            "relay": relay_line or plant_relay,
            # Pass only needed slices — never nest full event.extra (circular JSON).
            "channel_map": extra_ev.get("channel_map"),
            "digital_map": extra_ev.get("digital_map"),
            "cause_evidence": extra_ev.get("cause_evidence"),
            "multi_end": extra_ev.get("multi_end"),
            "asset_type": extra_ev.get("asset_type"),
            "asset_name": extra_ev.get("asset_name"),
            "lightning_csv": extra_ev.get("lightning_csv"),
            "event_datetime": (
                event.event_datetime.isoformat()
                if isinstance(event.event_datetime, datetime)
                else event.event_datetime
            ),
            "extra": {
                k: extra_ev.get(k)
                for k in (
                    "cause_evidence",
                    "asset_type",
                    "asset_name",
                    "lightning_csv",
                    "digital_map",
                    "channel_map",
                )
                if extra_ev.get(k) is not None
            },
        },
        setting_candidates=setting_candidates or None,
        relay_settings=relay_settings or None,
        line_params=line_params or None,
        ct_vt_ratios=ct_vt_ratios or None,
        extra_timeline=extra_timeline or None,
    )

    # Clear prior engineering rows for this event (keep COMTRADE file/channels)
    for model in (
        Measurement,
        EventTimeline,
        ProtectionOperation,
        ConsistencyFinding,
        FaultClassification,
        RcaHypothesis,
        Evidence,
    ):
        await db.execute(delete(model).where(model.event_id == event.id))
    await db.flush()

    # Electrical / RMS + phasor measurements (units normalized)
    from common.units import infer_unit_from_quantity, normalize_unit

    elec = result.electrical_analysis or {}
    roles = elec.get("channel_roles") or {}
    rms = elec.get("rms") or {}
    for name, payload in list(rms.items())[:24]:
        if not isinstance(payload, dict):
            continue
        role = str(roles.get(name) or "")
        unit = normalize_unit(payload.get("unit"), role=role) or infer_unit_from_quantity(
            f"{name}_rms", ""
        )
        db.add(
            Measurement(
                event_id=event.id,
                quantity=f"{name}_rms",
                phase=role[-1] if role in ("IA", "IB", "IC", "VA", "VB", "VC") else None,
                value=payload.get("value") if payload.get("status") == "OK" else None,
                unit=unit or None,
                algorithm="electrical_analysis",
                algorithm_version=settings.signal_algorithm_version,
                quality=payload.get("status") or "NOT_VALIDATED",
                extra=payload,
            )
        )

    phasors = elec.get("phasors") or {}
    for name, payload in list(phasors.items())[:24]:
        if not isinstance(payload, dict) or payload.get("status") != "OK":
            continue
        val = payload.get("value") if isinstance(payload.get("value"), dict) else {}
        role = str(roles.get(name) or "")
        unit = normalize_unit(payload.get("unit"), role=role) or infer_unit_from_quantity(name, "")
        mag = val.get("magnitude")
        ang = val.get("angle_deg")
        db.add(
            Measurement(
                event_id=event.id,
                quantity=f"{name}_phasor",
                phase=role[-1] if role in ("IA", "IB", "IC", "VA", "VB", "VC") else None,
                value=float(mag) if mag is not None else None,
                unit=unit or None,
                algorithm="electrical_analysis",
                algorithm_version=settings.signal_algorithm_version,
                quality=payload.get("status") or "NOT_VALIDATED",
                vector={"mag": mag, "angle_deg": ang, "real": val.get("real"), "imag": val.get("imag")},
                extra=payload,
            )
        )

    for key, label_prefix, default_unit in (
        ("current_sequences", "I", "A"),
        ("voltage_sequences", "V", "V"),
    ):
        seq = (elec.get("sequences") or {}).get(key)
        if not isinstance(seq, dict) or seq.get("status") != "OK":
            continue
        sval = seq.get("value") if isinstance(seq.get("value"), dict) else {}
        unit = normalize_unit(seq.get("unit"), role=label_prefix) or default_unit
        for comp, qname in (("positive", f"{label_prefix}1"), ("negative", f"{label_prefix}2"), ("zero", f"{label_prefix}0")):
            cval = sval.get(comp) if isinstance(sval.get(comp), dict) else {}
            mag = cval.get("magnitude")
            ang = cval.get("angle_deg")
            if mag is None and "real" in cval and "imag" in cval:
                try:
                    mag = (float(cval["real"]) ** 2 + float(cval["imag"]) ** 2) ** 0.5
                except (TypeError, ValueError):
                    mag = None
            db.add(
                Measurement(
                    event_id=event.id,
                    quantity=qname,
                    phase=comp[:3].upper(),
                    value=float(mag) if mag is not None else None,
                    unit=unit,
                    algorithm="electrical_analysis",
                    algorithm_version=settings.signal_algorithm_version,
                    quality=seq.get("status") or "NOT_VALIDATED",
                    vector={"mag": mag, "angle_deg": ang},
                    extra={"component": comp, "source": key},
                )
            )

    for phase_key, zpay in list((elec.get("impedance") or {}).items())[:12]:
        if not isinstance(zpay, dict) or zpay.get("status") != "OK":
            continue
        zval = zpay.get("value") if isinstance(zpay.get("value"), dict) else {}
        mag = zval.get("magnitude")
        ang = zval.get("angle_deg")
        if str(phase_key).startswith("loop_"):
            loop = str(phase_key).replace("loop_", "").upper()
            quantity = f"Z_{loop}"
            phase = loop
        else:
            phase = str(phase_key).replace("phase_", "").upper()
            quantity = f"Z_{phase}"
        db.add(
            Measurement(
                event_id=event.id,
                quantity=quantity,
                phase=phase,
                value=float(mag) if mag is not None else None,
                unit="Ω",
                algorithm="electrical_analysis",
                algorithm_version=settings.signal_algorithm_version,
                quality=zpay.get("status") or "NOT_VALIDATED",
                vector={"mag": mag, "angle_deg": ang, "R": zval.get("R"), "X": zval.get("X")},
                extra=zpay,
            )
        )

    # Power (SIGRA calculates P/Q/S from recorded fault data)
    for phase_key, ppay in list((elec.get("power") or {}).items())[:6]:
        if not isinstance(ppay, dict) or ppay.get("status") != "OK":
            continue
        pval = ppay.get("value") if isinstance(ppay.get("value"), dict) else {}
        phase = phase_key.replace("phase_", "").upper()
        unit = str(ppay.get("unit") or "VA")
        for qty, key in (("P", "P"), ("Q", "Q"), ("S", "S")):
            if pval.get(key) is None and pval.get(qty) is None:
                continue
            raw = pval.get(key, pval.get(qty))
            try:
                num = float(raw)
            except (TypeError, ValueError):
                continue
            db.add(
                Measurement(
                    event_id=event.id,
                    quantity=f"{qty}_{phase}",
                    phase=phase,
                    value=num,
                    unit="W" if qty == "P" else ("var" if qty == "Q" else unit),
                    algorithm="electrical_analysis",
                    algorithm_version=settings.signal_algorithm_version,
                    quality=ppay.get("status") or "NOT_VALIDATED",
                    extra=ppay,
                )
            )

    # Timeline
    for i, te in enumerate(result.timeline or []):
        t_s = te.get("timestamp")
        t_us = int(float(t_s) * 1_000_000) if t_s is not None else None
        etype = str(te.get("event_type") or "EVENT").upper()
        meta_te = te.get("metadata") if isinstance(te.get("metadata"), dict) else {}
        abs_t = meta_te.get("absolute_time")
        abs_dt = None
        if abs_t:
            try:
                s = str(abs_t).replace("Z", "+00:00")
                abs_dt = datetime.fromisoformat(s)
            except ValueError:
                abs_dt = None
        db.add(
            EventTimeline(
                event_id=event.id,
                sequence=i + 1,
                t_us=t_us,
                absolute_time=abs_dt,
                event_type=etype,
                source=str(te.get("source") or "COMTRADE"),
                label=str(
                    meta_te.get("label")
                    or meta_te.get("signal")
                    or te.get("event_type")
                    or "event"
                ),
                description=json.dumps(meta_te or te.get("metadata") or {})[:500],
                confidence=_conf_float(te.get("confidence")),
                payload=te,
            )
        )

    # Protection operations — persist every assessment (details carry full row for reports)
    for a in result.protection_assessment or []:
        element = str(a.get("element") or "UNKNOWN")
        trip = a.get("trip")
        pickup = a.get("pickup")
        if trip:
            op_type = "TRIP"
        elif pickup:
            op_type = "PICKUP"
        else:
            op_type = "ASSESSMENT"
        timing = a.get("timing") if isinstance(a.get("timing"), dict) else {}
        t_pickup_us = None
        t_trip_us = None
        try:
            if timing.get("pickup_time_s") is not None:
                t_pickup_us = int(round(float(timing["pickup_time_s"]) * 1e6))
        except (TypeError, ValueError):
            t_pickup_us = None
        try:
            if timing.get("trip_time_s") is not None:
                t_trip_us = int(round(float(timing["trip_time_s"]) * 1e6))
        except (TypeError, ValueError):
            t_trip_us = None
        db.add(
            ProtectionOperation(
                event_id=event.id,
                element=element,
                function_code=element,
                operation_type=op_type,
                asserted=bool(trip or pickup),
                expected=a.get("expected_operation") == "OPERATE",
                confidence=_conf_float(a.get("confidence")),
                t_pickup_us=t_pickup_us,
                t_trip_us=t_trip_us,
                details=a,
            )
        )

    # Consistency
    for f in result.consistency_findings or []:
        conf = f.get("confidence")
        try:
            conf_f = float(conf) if isinstance(conf, (int, float)) else _conf_float(conf)
        except (TypeError, ValueError):
            conf_f = None
        db.add(
            ConsistencyFinding(
                event_id=event.id,
                element=str(f.get("element") or "GENERAL"),
                check_type=str(f.get("check_type") or "ASSESSMENT"),
                setting_source=f.get("setting_source") or extra.get("setting_source"),
                setting_version=f.get("setting_version") or extra.get("setting_version"),
                expected=f.get("expected") if isinstance(f.get("expected"), dict) else {"value": f.get("expected")},
                observed=f.get("observed") if isinstance(f.get("observed"), dict) else {"value": f.get("observed")},
                status=str(f.get("status") or "UNVERIFIABLE"),
                severity=str(f.get("severity") or "MEDIUM"),
                explanation=str(f.get("explanation") or ""),
                confidence=conf_f,
                evidence_ids=f.get("evidence_ids"),
                rule_version=settings.consistency_rules_version,
            )
        )

    # Fault
    fault = result.fault_classification or {}
    feat = fault.get("evidence") or {}
    phases = [p for p, flag in (("A", "Ia_elevated"), ("B", "Ib_elevated"), ("C", "Ic_elevated")) if feat.get(flag)]
    dist = fault.get("distance") or {}
    loop_z = dist.get("loop_impedance") if isinstance(dist.get("loop_impedance"), dict) else {}
    conf_level = str(fault.get("confidence") or "INCONCLUSIVE")
    z_mag = loop_z.get("magnitude_ohm")
    z_ang = loop_z.get("angle_deg")
    z_r = loop_z.get("R_ohm")
    dist_applicable = bool(feat.get("distance_applicable"))
    if str(dist.get("status") or "").upper() == "NOT_APPLICABLE":
        dist_applicable = False
    fault_limits = list(fault.get("limitations") or [])
    if not dist_applicable:
        fault_limits = [
            lim
            for lim in fault_limits
            if "FAULT DISTANCE" not in str(lim).upper() and "Z1/KM" not in str(lim).upper()
        ]
        loop_z = {}
        z_mag = None
        z_ang = None
        z_r = None
    expl = "; ".join(fault_limits) if fault_limits else None
    if not expl and dist_applicable:
        expl = dist.get("reason") or None
    db.add(
        FaultClassification(
            event_id=event.id,
            fault_type=str(fault.get("fault_type") or "UNKNOWN"),
            status=str(fault.get("status") or "INCONCLUSIVE"),
            involved_phases=phases or None,
            ground_involved=feat.get("ground"),
            distance_km=dist.get("value_km") if dist_applicable else None,
            location_method=(str(dist.get("method") or "") or None) if dist_applicable else None,
            impedance_ohm=float(z_mag) if z_mag is not None else None,
            impedance_angle_deg=float(z_ang) if z_ang is not None else None,
            resistance_ohm=float(z_r) if z_r is not None else None,
            explanation=expl,
            confidence=_conf_float(conf_level),
            confidence_level=conf_level,
            features={
                **feat,
                "distance_applicable": dist_applicable,
                "location_algorithms": (dist.get("algorithms") or feat.get("location_algorithms") or [])
                if dist_applicable
                else [],
                "line_impedance_estimate": (
                    dist.get("line_impedance_estimate")
                    or feat.get("line_impedance_estimate")
                    or {}
                )
                if dist_applicable
                else {"status": "NOT_APPLICABLE"},
                "loop_impedance": loop_z or {},
                "distance_detail": {
                    "status": dist.get("status")
                    or ("NOT_APPLICABLE" if not dist_applicable else None),
                    "method": dist.get("method") if dist_applicable else None,
                    "loop_source": dist.get("loop_source") if dist_applicable else None,
                    "reason": dist.get("reason") if dist_applicable else None,
                    "algorithms": (dist.get("algorithms") or []) if dist_applicable else [],
                },
            },
            classifier_version=str(fault.get("algorithm_version") or settings.signal_algorithm_version),
            is_primary=True,
        )
    )

    # RCA
    rca = result.rca_hypotheses or {}
    hyps = rca.get("hypotheses") or rca.get("ranked") or []
    primary = rca.get("primary") if isinstance(rca.get("primary"), dict) else None
    # Ensure primary is ranked first when present
    ordered: list[dict[str, Any]] = []
    if primary and primary.get("hypothesis_id"):
        ordered.append(primary)
    for h in hyps:
        if not isinstance(h, dict):
            continue
        if primary and h.get("hypothesis_id") == primary.get("hypothesis_id"):
            continue
        ordered.append(h)

    for i, h in enumerate(ordered[:12], start=1):
        hid = str(h.get("hypothesis_id") or h.get("code") or f"H{i}")
        statement = str(
            h.get("statement")
            or f"Status={h.get('status')}; score={h.get('score', 0)}"
        )
        db.add(
            RcaHypothesis(
                event_id=event.id,
                hypothesis_code=hid,
                title=str(h.get("title") or hid.replace("_", " ").title()),
                statement=statement,
                status=str(h.get("status") or "INCONCLUSIVE"),
                rank=i,
                confidence=float(h.get("score") or _conf_float(h.get("confidence")) or 0.0),
                confidence_level=str(h.get("confidence") or "INCONCLUSIVE"),
                supporting_evidence_ids=h.get("supporting_evidence")
                or h.get("supporting_evidence_ids"),
                contradicting_evidence_ids=h.get("contradicting_evidence")
                or h.get("contradicting_evidence_ids"),
                causal_chain=h.get("causal_chain") or None,
                engine_version=settings.rca_engine_version,
                explanation=str(h.get("explanation") or "") or None,
                recommended_actions=h.get("recommended_actions")
                or [
                    "Verify active setting group",
                    "Review consistency findings",
                    "Confirm channel mapping vs plant",
                ],
                extra={
                    "raw": h,
                    "missing_evidence": h.get("missing_evidence"),
                    "is_primary": i == 1,
                },
            )
        )

    # Evidence — store human-readable titles / polarity for the Evidence tab
    for ev in result.evidence or []:
        if not isinstance(ev, dict):
            continue
        title, summary, polarity, key = _humanize_evidence(ev)
        t_us = None
        ts = ev.get("timestamp")
        if isinstance(ts, (int, float)):
            # Pipeline timestamps may be seconds or already µs; treat small as seconds
            t_us = int(ts * 1_000_000) if abs(ts) < 10_000 else int(ts)
        db.add(
            Evidence(
                event_id=event.id,
                evidence_key=key,
                source_type=str(ev.get("source_type") or "CALCULATION"),
                polarity=polarity,
                title=title[:255],
                summary=summary[:2000],
                confidence=_conf_float(ev.get("confidence")),
                t_us=t_us,
                references={
                    "parameter": ev.get("parameter"),
                    "expected": ev.get("expected"),
                    "observed": ev.get("observed"),
                    "value": ev.get("value"),
                    "unit": ev.get("unit"),
                    "source_id": ev.get("source_id"),
                },
                raw=ev,
            )
        )

    decision = result.decision or {}
    event.decision_state = str(
        decision.get("state") or decision.get("status") or "ENGINEER_REVIEW_REQUIRED"
    )
    # Summary fields for event header / list — fault-aware (not flat HIGH for every fault)
    from consistency.severity import event_severity_summary

    ft = str(fault.get("fault_type") or "UNKNOWN")
    extra["fault_type"] = ft
    operated_codes: list[str] = []
    seen: set[str] = set()
    for a in result.protection_assessment or []:
        if not isinstance(a, dict):
            continue
        if not (a.get("trip") or a.get("pickup")):
            continue
        code = str(a.get("element") or a.get("function_code") or "").strip()
        if not code or code.upper() == "UNKNOWN":
            continue
        key = code.upper()
        if key in seen:
            continue
        seen.add(key)
        operated_codes.append(code)
    # Prefer ANSI-like codes first (digits), stable order
    operated_codes.sort(
        key=lambda c: (0 if any(ch.isdigit() for ch in c) else 1, c.upper())
    )
    extra["protection_summary"] = ", ".join(operated_codes) if operated_codes else None
    sevs = [
        str(f.get("severity") or "")
        for f in (result.consistency_findings or [])
        if isinstance(f, dict) and f.get("severity")
    ]
    extra["severity_summary"] = event_severity_summary(
        finding_severities=sevs,
        fault_type=ft,
        fault_status=str(fault.get("status") or ""),
    )
    # Event datetime from COMTRADE trigger / start when wizard left it empty
    if event.event_datetime is None:
        ts = record.trigger_time or record.start_time
        if ts is not None:
            try:
                if hasattr(ts, "tzinfo"):
                    event.event_datetime = ts
                else:
                    event.event_datetime = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            except Exception:  # noqa: BLE001
                pass

    if result.limitations:
        lims = list(result.limitations[:20])
        if not (fault.get("evidence") or {}).get("distance_applicable"):
            lims = [
                lim
                for lim in lims
                if "FAULT DISTANCE" not in str(lim).upper() and "Z1/KM" not in str(lim).upper()
            ]
        extra["analysis_limitations"] = lims

    if distance_zones:
        extra["distance_zones"] = distance_zones

    # Slim electrical summary for reports (avoid storing full phasor payloads)
    elec_full = result.electrical_analysis or {}
    rms_summary: dict[str, Any] = {}
    for name, payload in list((elec_full.get("rms") or {}).items())[:24]:
        if isinstance(payload, dict):
            rms_summary[name] = {
                "value": payload.get("value"),
                "unit": payload.get("unit"),
                "status": payload.get("status"),
            }
    # Cap heatmap storage (time × order for ≤3 channels)
    heatmap_raw = elec_full.get("harmonics_heatmap") or {}
    heatmap_slim: dict[str, Any] = {}
    if isinstance(heatmap_raw, dict):
        for i, (ch, payload) in enumerate(heatmap_raw.items()):
            if i >= 3 or not isinstance(payload, dict):
                continue
            if payload.get("status") != "OK":
                continue
            heatmap_slim[ch] = {
                "status": "OK",
                "channel": ch,
                "unit": payload.get("unit"),
                "times_s": list(payload.get("times_s") or [])[:48],
                "harmonics_rms": {
                    str(k): list(v)[:48]
                    for k, v in (payload.get("harmonics_rms") or {}).items()
                    if str(k).isdigit() and int(k) <= 7
                },
                "method": payload.get("method"),
            }
    setting_ref = dict(result.setting_reference or {})
    setting_ref.update(
        {
            k: v
            for k, v in {
                "setting_source_used": setting_ref.get("setting_source_used")
                or extra.get("setting_source"),
                "setting_version": setting_ref.get("setting_version")
                or extra.get("setting_version"),
                "setting_group": setting_ref.get("setting_group")
                or extra.get("setting_group"),
                "active_setting_group_verification": setting_ref.get(
                    "active_setting_group_verification"
                )
                or extra.get("active_group_status"),
                "setting_approval": extra.get("setting_approval"),
                "setting_file": extra.get("setting_file"),
                "param_count": extra.get("setting_param_count"),
            }.items()
            if v is not None
        }
    )
    if extra.get("settings_file_verification_note") and not setting_ref.get("explanation"):
        setting_ref["explanation"] = extra["settings_file_verification_note"]
    # Full analysis dict for HTML report export (matches ReportGenerator template)
    # Copy only scalar-ish event fields — never nest event.extra (circular JSON on flush).
    src_ev = result.event if isinstance(result.event, dict) else {}
    event_for_report = {
        k: v
        for k, v in src_ev.items()
        if k not in ("extra", "report_analysis") and not isinstance(v, (dict, list))
    }
    # Allow a few known nested-safe keys if present as plain values already filtered
    for k in ("event_id", "description", "substation", "bay", "feeder", "asset", "relay", "nominal_voltage_kv"):
        if k in src_ev and k not in event_for_report:
            val = src_ev[k]
            if not isinstance(val, (dict, list)):
                event_for_report[k] = val
    event_for_report.setdefault("event_id", event.event_id)
    event_for_report.setdefault("description", event.description)
    event_for_report["asset"] = asset_line or event_for_report.get("asset")
    event_for_report["relay"] = relay_line or event_for_report.get("relay")
    extra["report_analysis"] = {
        "event": event_for_report,
        "data_quality": result.data_quality or {},
        "electrical_analysis": {
            "limitations": elec_full.get("limitations") or [],
            "sample_rate_hz": elec_full.get("sample_rate_hz"),
            "nominal_frequency_hz": elec_full.get("nominal_frequency_hz"),
            "channel_roles": elec_full.get("channel_roles") or {},
            "rms": rms_summary,
            "harmonics": elec_full.get("harmonics") or {},
            "harmonics_heatmap": heatmap_slim,
            "detectors": elec_full.get("detectors") or {},
            "impedance": elec_full.get("impedance") or {},
            "phasors": elec_full.get("phasors") or {},
        },
        "timeline": list(result.timeline or []),
        "protection_assessment": list(result.protection_assessment or []),
        "consistency_findings": list(result.consistency_findings or []),
        "fault_classification": result.fault_classification or {},
        "breaker_analysis": result.breaker_analysis or {},
        "rca_hypotheses": result.rca_hypotheses or {},
        "enrichment": (result.rca_hypotheses or {}).get("enrichment") or {},
        "scheme": (result.rca_hypotheses or {}).get("scheme") or {},
        "distance_zones": distance_zones,
        "evidence": list(result.evidence or [])[:50],
        "similar_events": result.similar_events
        or {"message": "SIMILARITY RESULT: NOT AVAILABLE"},
        "decision": decision,
        "limitations": list(result.limitations or []),
        "setting_reference": setting_ref,
        "engineer_review": "PENDING",
    }
    event.extra = _json_safe(extra)
    try:
        from sqlalchemy.orm.attributes import flag_modified

        flag_modified(event, "extra")
    except Exception:  # noqa: BLE001
        pass

    await db.flush()
    return {
        "success": True,
        "fault_type": fault.get("fault_type"),
        "decision": event.decision_state,
        "timeline_events": len(result.timeline or []),
        "hypotheses": len(hyps),
        "limitations": result.limitations[:10],
    }
