"""Analysis API — enqueue jobs and fetch stage results (read-only; no control)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from sqlalchemy import select

from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import (
    ComtradeChannel,
    ComtradeFile,
    ConsistencyFinding,
    EventFile,
    EventTimeline,
    Evidence,
    FaultClassification,
    Measurement,
    ProtectionOperation,
    RcaHypothesis,
    User,
)
from app.schemas.analysis import (
    AnalyseRequest,
    AnalyseResponse,
    AnalysisJobOut,
    ElectricalSummaryOut,
    FaultCharacteristicsOut,
    FaultClassificationOut,
    FaultLocationRowOut,
    ProtectionSummaryOut,
    TimelineEntryOut,
    WaveformChannelOut,
    WaveformMarkerOut,
    WaveformsResponse,
)
from app.schemas.comtrade import ComtradeFileOut
from app.schemas.consistency import ConsistencyFindingOut, ConsistencyListResponse
from app.schemas.evidence import EvidenceListResponse, EvidenceOut
from app.schemas.rca import RcaHypothesisOut, RcaResponse, SupportingScoreOut
from app.services import analysis_service, event_service

router = APIRouter(prefix="/api", tags=["analysis"])


def _rca_supporting_scores(event) -> dict[str, SupportingScoreOut] | None:
    """Surface ML/similarity availability from persisted report_analysis (ML-014)."""
    extra = event.extra if isinstance(getattr(event, "extra", None), dict) else {}
    ra = extra.get("report_analysis") if isinstance(extra.get("report_analysis"), dict) else {}
    rca = ra.get("rca_hypotheses") if isinstance(ra.get("rca_hypotheses"), dict) else {}
    raw = rca.get("supporting_scores")
    if not isinstance(raw, dict):
        raw = ra.get("supporting_scores") if isinstance(ra.get("supporting_scores"), dict) else None
    if not isinstance(raw, dict):
        # Derive from similar_events / anomalies blobs when older analyses lack the block
        sim = ra.get("similar_events") if isinstance(ra.get("similar_events"), dict) else {}
        anom = ra.get("anomalies") if isinstance(ra.get("anomalies"), dict) else {}
        sim_ok = str(sim.get("status") or "").upper() == "OK"
        ml_ok = str(anom.get("status") or "").upper() == "OK"
        raw = {
            "ml": {
                "available": ml_ok,
                "status": "OK" if ml_ok else "NOT_AVAILABLE",
                "message": None if ml_ok else (anom.get("message") or "ML RESULT: NOT AVAILABLE"),
            },
            "similarity": {
                "available": sim_ok,
                "status": "OK" if sim_ok else "NOT_AVAILABLE",
                "message": None
                if sim_ok
                else (sim.get("message") or "SIMILARITY RESULT: NOT AVAILABLE"),
            },
        }
    out: dict[str, SupportingScoreOut] = {}
    for key in ("ml", "similarity"):
        block = raw.get(key)
        if isinstance(block, dict):
            out[key] = SupportingScoreOut.model_validate(block)
        else:
            out[key] = SupportingScoreOut()
    return out

_SETTING_PLACEHOLDERS = {
    "",
    "N/A",
    "NA",
    "NONE",
    "MIXED",
    "NOT AVAILABLE",
    "NOT_AVAILABLE",
}


def _bound_setting_value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.upper().replace("_", " ") in _SETTING_PLACEHOLDERS:
        return None
    return text


async def _settings_file_checksum(db: DbSession, event_id: str, setting_file: object) -> str | None:
    rows = (
        await db.execute(select(EventFile).where(EventFile.event_id == event_id))
    ).scalars().all()
    settings = [f for f in rows if (f.source_type or "").upper() == "SETTINGS"]
    name = str(setting_file or "").lower()
    if name:
        for f in settings or rows:
            orig = (f.original_filename or "").lower()
            if name in orig or orig.endswith(name) or orig in name:
                return f.sha256
    if settings:
        return settings[0].sha256
    return None


@router.post("/analyse", response_model=AnalyseResponse)
async def analyse(
    body: AnalyseRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
) -> AnalyseResponse:
    event = await event_service.get_event(db, body.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    params = dict(body.parameters or {})
    # Combined RCA product removed — always analyse as a single event
    params.pop("analysis_mode", None)
    params.pop("peer_event_id", None)
    params.pop("combined_ready", None)

    # Queue job and return immediately — long COMTRADE engineering must not
    # hold the HTTP request open (browser shows "Network Error" on drop/timeout).
    job = await analysis_service.enqueue_analysis(
        db,
        event,
        requested_by=user.id,
        parameters=params or None,
        force=body.force,
        request_id=getattr(request.state, "request_id", None),
        defer=True,
    )
    # Commit before background so the new session can see the job row.
    await db.commit()
    if job.status == "PENDING":
        # Dual schedule: create_task is primary (EXE-reliable); BackgroundTasks backup.
        analysis_service.schedule_deferred_job(job.id)
        background_tasks.add_task(analysis_service.run_job_by_id, job.id)
    return AnalyseResponse(
        job=AnalysisJobOut.model_validate(job),
        message="Analysis queued — progress updates on this page",
    )


@router.get("/analysis-status/{job_id}", response_model=AnalysisJobOut)
async def analysis_status(
    job_id: str, db: DbSession, user: CurrentUser
) -> AnalysisJobOut:
    job = await analysis_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return AnalysisJobOut.model_validate(job)


@router.get("/events/{event_id}/analysis-status", response_model=AnalysisJobOut)
async def analysis_status_for_event(
    event_id: str, db: DbSession, user: CurrentUser
) -> AnalysisJobOut:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    job = await analysis_service.latest_job_for_event(db, event.id)
    if job is None:
        raise HTTPException(status_code=404, detail="No analysis job for event")

    # Soft re-kick: still PENDING after a few seconds → background task likely dropped.
    age = analysis_service._job_age_seconds(job)
    if (
        str(job.status or "").upper() == "PENDING"
        and float(job.progress or 0) <= 0.01
        and not job.started_at
        and 6.0 <= age < 25.0
    ):
        analysis_service.rekick_pending_job(job.id)

    job = await analysis_service.heal_stuck_analysis(db, event, job)
    if job is None:
        raise HTTPException(status_code=404, detail="No analysis job for event")
    await db.commit()
    return AnalysisJobOut.model_validate(job)


@router.get("/events/{event_id}/timeline", response_model=list[TimelineEntryOut])
async def get_timeline(
    event_id: str, db: DbSession, user: CurrentUser
) -> list[TimelineEntryOut]:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    rows = (
        await db.execute(
            select(EventTimeline)
            .where(EventTimeline.event_id == event.id)
            .order_by(EventTimeline.sequence)
        )
    ).scalars().all()
    return [TimelineEntryOut.model_validate(r) for r in rows]


@router.get("/events/{event_id}/comtrade", response_model=ComtradeFileOut)
async def get_event_comtrade(
    event_id: str, db: DbSession, user: CurrentUser
) -> ComtradeFileOut:
    """Return parsed COMTRADE metadata for the event (created during analysis)."""
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    ct = (
        await db.execute(
            select(ComtradeFile)
            .where(ComtradeFile.event_id == event.id)
            .order_by(ComtradeFile.created_at.desc())
        )
    ).scalars().first()
    if ct is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "COMTRADE metadata not available yet. "
                "Upload CFG/DAT (or a ZIP containing them), then start analysis."
            ),
        )
    meta = ct.header_metadata if isinstance(ct.header_metadata, dict) else {}
    out = ComtradeFileOut.model_validate(ct)
    return out.model_copy(
        update={
            "format_detected": meta.get("data_format") or meta.get("standard"),
            "support_status": ct.validation_status,
        }
    )


@router.get("/events/{event_id}/waveforms", response_model=WaveformsResponse)
async def get_waveforms(
    event_id: str,
    db: DbSession,
    user: CurrentUser,
    comtrade_file_id: Optional[str] = Query(None),
) -> WaveformsResponse:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    from app.core.config import get_settings
    from app.services.waveform_service import load_waveform_payload

    settings = get_settings()
    payload = await load_waveform_payload(
        db,
        event.id,
        comtrade_file_id=comtrade_file_id,
        max_channels=settings.waveform_max_channels,
    )
    out = []
    for c in payload.get("channels") or []:
        samples = c.get("samples")
        if not samples:
            continue
        timestamps = c.get("timestamps_us")
        if not timestamps or len(timestamps) != len(samples):
            # Synthesize µs axis when CFG/DAT timestamps are missing
            timestamps = [float(i) for i in range(len(samples))]
        out.append(
            WaveformChannelOut(
                name=c["name"],
                channel_type=c["channel_type"],
                phase=c.get("phase"),
                units=c.get("units"),
                sample_count=len(samples),
                samples=[float(v) if v is not None else 0.0 for v in samples],
                timestamps_us=[float(t) for t in timestamps],
            )
        )
    markers = [
        WaveformMarkerOut(
            t_us=float(m.get("t_us") or 0),
            label=str(m.get("label") or "marker"),
            color=m.get("color"),
        )
        for m in payload.get("markers") or []
    ]
    return WaveformsResponse(
        event_id=event.id,
        channels=out,
        markers=markers,
        note=payload.get("note") if out else (payload.get("note") or "No waveform samples cached"),
    )


@router.get("/events/{event_id}/electrical", response_model=ElectricalSummaryOut)
async def get_electrical(
    event_id: str, db: DbSession, user: CurrentUser
) -> ElectricalSummaryOut:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    rows = (
        await db.execute(select(Measurement).where(Measurement.event_id == event.id))
    ).scalars().all()
    measurements = [
        {
            "id": m.id,
            "quantity": m.quantity,
            "phase": m.phase,
            "value": m.value,
            "unit": m.unit,
            "quality": m.quality,
            "algorithm": m.algorithm,
            "vector": m.vector,
            "event_id": event.id,
        }
        for m in rows
    ]
    return ElectricalSummaryOut(event_id=event.id, measurements=measurements)


@router.get("/events/{event_id}/protection", response_model=ProtectionSummaryOut)
async def get_protection(
    event_id: str, db: DbSession, user: CurrentUser
) -> ProtectionSummaryOut:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    rows = (
        await db.execute(
            select(ProtectionOperation).where(ProtectionOperation.event_id == event.id)
        )
    ).scalars().all()
    ops = [
        {
            "id": o.id,
            "event_id": event.id,
            "element": o.element,
            "function_code": o.function_code,
            "operation_type": o.operation_type,
            "asserted": o.asserted,
            "t_pickup_us": o.t_pickup_us,
            "t_trip_us": o.t_trip_us,
            "expected": o.expected,
            "confidence": o.confidence,
            "breaker_assessment": o.breaker_assessment,
            "details": o.details,
        }
        for o in rows
    ]
    return ProtectionSummaryOut(event_id=event.id, operations=ops)


@router.get("/events/{event_id}/consistency", response_model=ConsistencyListResponse)
async def get_consistency(
    event_id: str, db: DbSession, user: CurrentUser
) -> ConsistencyListResponse:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    rows = (
        await db.execute(
            select(ConsistencyFinding).where(ConsistencyFinding.event_id == event.id)
        )
    ).scalars().all()
    findings = [ConsistencyFindingOut.model_validate(r) for r in rows]
    inconsistent = sum(1 for f in findings if f.status == "INCONSISTENT")
    consistent = sum(1 for f in findings if f.status == "CONSISTENT")
    unverifiable = sum(1 for f in findings if f.status == "UNVERIFIABLE")
    dq_issue = sum(1 for f in findings if f.status == "DATA_QUALITY_ISSUE")
    # UNVERIFIABLE rows must not paint overall yellow when checks also passed
    if inconsistent:
        overall = "INCONSISTENT"
    elif consistent:
        overall = "CONSISTENT"
    elif dq_issue:
        overall = "DATA_QUALITY_ISSUE"
    elif unverifiable:
        overall = "UNVERIFIABLE"
    elif findings:
        overall = "CONSISTENT"
    else:
        overall = "NOT_AVAILABLE"
    summary = {
        "total": len(findings),
        "consistent": consistent,
        "inconsistent": inconsistent,
        "unverifiable": unverifiable,
        "data_quality_issue": dq_issue,
        "high_severity": sum(
            1 for f in findings if (f.severity or "").upper() in ("HIGH", "CRITICAL")
        ),
    }
    extra = event.extra if isinstance(event.extra, dict) else {}
    plant = extra.get("plant_labels") if isinstance(extra.get("plant_labels"), dict) else {}
    src = _bound_setting_value(extra.get("setting_source"))
    ver = _bound_setting_value(extra.get("setting_version"))
    for f in findings:
        if src is None:
            src = _bound_setting_value(f.setting_source)
        if ver is None:
            ver = _bound_setting_value(f.setting_version)
        if src and ver:
            break
    checksum = extra.get("setting_checksum") or extra.get("checksum")
    if not checksum:
        checksum = await _settings_file_checksum(db, event.id, extra.get("setting_file"))
    relay_tag = extra.get("relay_tag") or plant.get("relay_tag")
    setting_info = {
        "source": src or "NOT AVAILABLE",
        "version": ver or "NOT AVAILABLE",
        "group": extra.get("setting_group") or "—",
        "active_group_status": extra.get("active_group_status") or "NOT VERIFIED",
        "verification_state": extra.get("active_group_status") or "NOT VERIFIED",
        "approval_status": extra.get("setting_approval") or "NOT VERIFIED",
        "relay_tag": relay_tag,
        "effective_from": extra.get("setting_effective_from") or extra.get("effective_from"),
        "checksum": checksum,
    }
    return ConsistencyListResponse(
        event_id=event.id,
        findings=findings,
        summary=summary,
        overall_status=overall,
        setting_source=setting_info,
    )


@router.get("/events/{event_id}/fault", response_model=list[FaultClassificationOut])
async def get_fault(
    event_id: str, db: DbSession, user: CurrentUser
) -> list[FaultClassificationOut]:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    rows = (
        await db.execute(
            select(FaultClassification).where(FaultClassification.event_id == event.id)
        )
    ).scalars().all()
    out: list[FaultClassificationOut] = []
    for r in rows:
        item = FaultClassificationOut.model_validate(r)
        if item.impedance_ohm is None:
            feat = r.features if isinstance(r.features, dict) else {}
            loop = feat.get("loop_impedance") if isinstance(feat.get("loop_impedance"), dict) else {}
            if loop.get("magnitude_ohm") is not None:
                item = item.model_copy(
                    update={
                        "impedance_ohm": float(loop["magnitude_ohm"]),
                        "impedance_angle_deg": (
                            float(loop["angle_deg"]) if loop.get("angle_deg") is not None else None
                        ),
                    }
                )
        out.append(item)
    return out


@router.get(
    "/events/{event_id}/fault-characteristics",
    response_model=FaultCharacteristicsOut,
)
async def get_fault_characteristics(
    event_id: str, db: DbSession, user: CurrentUser
) -> FaultCharacteristicsOut:
    """AFAS-style fault characteristics + location algorithm suite."""
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    fault = (
        await db.execute(
            select(FaultClassification)
            .where(FaultClassification.event_id == event.id)
            .order_by(FaultClassification.is_primary.desc())
        )
    ).scalars().first()

    timeline = (
        await db.execute(
            select(EventTimeline)
            .where(EventTimeline.event_id == event.id)
            .order_by(EventTimeline.sequence)
        )
    ).scalars().all()

    def _first_t(*types: str) -> int | None:
        want = {t.upper() for t in types}
        for row in timeline:
            et = (row.event_type or "").upper()
            if any(w in et for w in want):
                return row.t_us
        return None

    feat = fault.features if fault and isinstance(fault.features, dict) else {}
    algs_raw = feat.get("location_algorithms") or []
    algorithms = [
        FaultLocationRowOut(
            algorithm=str(a.get("algorithm") or "Unknown"),
            status=str(a.get("status") or "NOT_CALCULABLE"),
            distance_km=a.get("distance_km"),
            distance_pct=a.get("distance_pct"),
            unit=str(a.get("unit") or "km"),
            notes=str(a.get("notes") or ""),
        )
        for a in algs_raw
        if isinstance(a, dict)
    ]

    limitations: list[str] = []
    if fault and fault.explanation:
        limitations = [p.strip() for p in str(fault.explanation).split(";") if p.strip()]

    # Non-fault DFR class (energization/motor/…) — do not publish shunt ground/phases
    ec = feat.get("event_class")
    if not ec:
        evc = feat.get("event_classification")
        if isinstance(evc, dict):
            ec = evc.get("event_class")
    shunt_fault = str(ec or "") == "FAULT"

    currents = {
        k: feat.get(k)
        for k in ("Ia", "Ib", "Ic", "I0", "I2", "Ia_elevated", "Ib_elevated", "Ic_elevated")
        if k in feat
    }
    if not shunt_fault:
        for k in ("Ia_elevated", "Ib_elevated", "Ic_elevated"):
            currents.pop(k, None)
    sequences = {
        "I0": feat.get("I0"),
        "I2": feat.get("I2"),
        "ground": feat.get("ground") if shunt_fault else None,
    }
    z_est = feat.get("line_impedance_estimate") if isinstance(feat.get("line_impedance_estimate"), dict) else {}
    from common.units import normalize_unit

    current_unit = normalize_unit(str(feat.get("current_unit") or ""), role="I") or "A"

    dist_detail = feat.get("distance_detail") if isinstance(feat.get("distance_detail"), dict) else {}
    raw_applicable = feat.get("distance_applicable")
    dist_status = str(dist_detail.get("status") or "").upper()
    if raw_applicable is False or dist_status == "NOT_APPLICABLE":
        distance_applicable = False
    elif raw_applicable is True:
        distance_applicable = True
    else:
        # Missing flag on legacy rows: do not unlock km from a stored distance_km alone
        distance_applicable = False

    # Harden response for differential / OC cases
    out_km = fault.distance_km if fault and distance_applicable else None
    out_method = fault.location_method if fault and distance_applicable else None
    out_algs = algorithms if distance_applicable else []
    out_z = z_est if distance_applicable else None
    if not distance_applicable:
        limitations = [
            lim
            for lim in limitations
            if "FAULT DISTANCE" not in lim.upper()
            and "Z1/KM" not in lim.upper()
            and "LINE Z1" not in lim.upper()
        ]

    out_phases = (fault.involved_phases if fault else None) if shunt_fault else None
    out_ground = (fault.ground_involved if fault else None) if shunt_fault else None

    elev_method = feat.get("elevation_method")
    prefault = feat.get("prefault_rms") if isinstance(feat.get("prefault_rms"), dict) else None
    fw = feat.get("fault_window") if isinstance(feat.get("fault_window"), dict) else None
    # Also pull from report snapshot / event.extra when features omitted
    if fw is None or prefault is None or not elev_method:
        evt_extra = event.extra if isinstance(event.extra, dict) else {}
        report = evt_extra.get("report_analysis") if isinstance(evt_extra.get("report_analysis"), dict) else {}
        elec = report.get("electrical_analysis") if isinstance(report.get("electrical_analysis"), dict) else {}
        det = elec.get("detectors") if isinstance(elec.get("detectors"), dict) else {}
        if fw is None and isinstance(det.get("fault_window"), dict):
            fw = det.get("fault_window")
        if prefault is None and isinstance(det.get("prefault_rms"), dict):
            prefault = det.get("prefault_rms")
        if not elev_method and prefault:
            elev_method = "prefault_ratio"

    return FaultCharacteristicsOut(
        event_id=event.id,
        fault_type=str(fault.fault_type if fault else "UNKNOWN"),
        status=str(fault.status if fault else "UNKNOWN"),
        confidence_level=fault.confidence_level if fault else None,
        involved_phases=out_phases,
        ground_involved=out_ground,
        distance_km=out_km,
        location_method=out_method,
        distance_applicable=bool(distance_applicable),
        inception_t_us=_first_t("INCEPTION", "FAULT") or (fault.inception_t_us if fault else None),
        pickup_t_us=_first_t("PICKUP"),
        trip_t_us=_first_t("TRIP"),
        clearing_t_us=_first_t("52A", "BREAKER", "CLEAR") or (fault.clearing_t_us if fault else None),
        currents=currents or None,
        sequences=sequences,
        current_unit=current_unit,
        impedance=dist_detail if distance_applicable else None,
        location_algorithms=out_algs,
        line_impedance_estimate=out_z or None,
        limitations=limitations,
        explanation=fault.explanation if fault else None,
        elevation_method=str(elev_method) if elev_method else None,
        prefault_rms=prefault,
        fault_window=fw,
    )


@router.get("/events/{event_id}/rca", response_model=RcaResponse)
async def get_rca(event_id: str, db: DbSession, user: CurrentUser) -> RcaResponse:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    rows = (
        await db.execute(
            select(RcaHypothesis)
            .where(RcaHypothesis.event_id == event.id)
            .order_by(RcaHypothesis.rank)
        )
    ).scalars().all()
    extra = event.extra if isinstance(event.extra, dict) else {}
    ra = extra.get("report_analysis") if isinstance(extra.get("report_analysis"), dict) else {}
    enrich = ra.get("enrichment") if isinstance(ra.get("enrichment"), dict) else {}
    matrix = ra.get("matrix") if isinstance(ra.get("matrix"), dict) else {}
    casc = extra.get("cascade") if isinstance(extra.get("cascade"), dict) else {}
    traces = list(enrich.get("matrix_traces") or casc.get("matrix_traces") or [])[:16]
    return RcaResponse(
        event_id=event.id,
        hypotheses=[RcaHypothesisOut.model_validate(r) for r in rows],
        decision_state=event.decision_state,
        supporting_scores=_rca_supporting_scores(event),
        enrichment=enrich or None,
        matrix=matrix or None,
        compound_class=(
            enrich.get("compound_class")
            or matrix.get("compound_class")
            or casc.get("compound_class")
        ),
        matrix_scenario=(
            enrich.get("matrix_scenario")
            or matrix.get("matched_scenario_id")
            or casc.get("matrix_scenario")
        ),
        matrix_traces=traces or None,
    )


@router.get("/events/{event_id}/cause-evidence")
async def get_cause_evidence(event_id: str, db: DbSession, user: CurrentUser):
    """Engineer / asset cause enrichment tags for RCA (deterministic)."""
    from rca.enrichment import TAG_CHOICES, normalize_cause_evidence

    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    extra = event.extra if isinstance(event.extra, dict) else {}
    items = normalize_cause_evidence(extra.get("cause_evidence"))
    ra = extra.get("report_analysis") if isinstance(extra.get("report_analysis"), dict) else {}
    return {
        "event_id": event_id,
        "items": items,
        "tag_choices": TAG_CHOICES,
        "asset_type": extra.get("asset_type"),
        "enrichment": ra.get("enrichment") or (ra.get("rca_hypotheses") or {}).get("enrichment"),
        "scheme": ra.get("scheme") or (ra.get("rca_hypotheses") or {}).get("scheme"),
    }


@router.put("/events/{event_id}/cause-evidence")
async def put_cause_evidence(
    event_id: str,
    body: dict,
    db: DbSession,
    user: User = Depends(require_role(Role.ANALYST)),
):
    from sqlalchemy.orm.attributes import flag_modified
    from rca.enrichment import normalize_cause_evidence

    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    cleaned = normalize_cause_evidence(body.get("items") or body.get("tokens") or body)
    extra = dict(event.extra) if isinstance(event.extra, dict) else {}
    extra["cause_evidence"] = cleaned
    if body.get("notes"):
        extra["cause_evidence_notes"] = str(body["notes"])[:2000]
    event.extra = extra
    flag_modified(event, "extra")
    await db.commit()
    return {
        "event_id": event_id,
        "items": cleaned,
        "saved": True,
        "message": "Cause evidence saved. Re-run analysis to re-score RCA hypotheses.",
    }


@router.get("/events/{event_id}/evidence", response_model=EvidenceListResponse)
async def get_evidence(
    event_id: str, db: DbSession, user: CurrentUser
) -> EvidenceListResponse:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    rows = (
        await db.execute(select(Evidence).where(Evidence.event_id == event.id))
    ).scalars().all()
    return EvidenceListResponse(
        event_id=event.id, items=[EvidenceOut.model_validate(r) for r in rows]
    )
