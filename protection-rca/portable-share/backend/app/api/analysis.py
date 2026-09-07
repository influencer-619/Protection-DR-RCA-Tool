"""Analysis API — enqueue jobs and fetch stage results (read-only; no control)."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select

from app.core.security import Role
from app.dependencies.auth import CurrentUser, DbSession, require_role
from app.models import (
    ComtradeChannel,
    ComtradeFile,
    ConsistencyFinding,
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
from app.schemas.rca import RcaHypothesisOut, RcaResponse
from app.services import analysis_service, event_service

router = APIRouter(prefix="/api", tags=["analysis"])


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
    # Queue job and return immediately — long COMTRADE engineering must not
    # hold the HTTP request open (browser shows "Network Error" on drop/timeout).
    job = await analysis_service.enqueue_analysis(
        db,
        event,
        requested_by=user.id,
        parameters=body.parameters,
        force=body.force,
        request_id=getattr(request.state, "request_id", None),
        defer=True,
    )
    # Commit before background so the new session can see the job row.
    await db.commit()
    if job.status == "PENDING":
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
    event_id: str, db: DbSession, user: CurrentUser
) -> WaveformsResponse:
    event = await event_service.get_event(db, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    from app.services.waveform_service import load_waveform_payload

    payload = await load_waveform_payload(db, event.id)
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
            "element": o.element,
            "function_code": o.function_code,
            "operation_type": o.operation_type,
            "asserted": o.asserted,
            "t_trip_us": o.t_trip_us,
            "confidence": o.confidence,
            "breaker_assessment": o.breaker_assessment,
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
    src = findings[0].setting_source if findings else None
    ver = findings[0].setting_version if findings else None
    extra = event.extra if isinstance(event.extra, dict) else {}
    plant = extra.get("plant_labels") if isinstance(extra.get("plant_labels"), dict) else {}
    setting_info = {
        "source": src or extra.get("setting_source") or "NOT VERIFIED",
        "version": ver or extra.get("setting_version") or "NOT VERIFIED",
        "group": extra.get("setting_group") or "NOT VERIFIED",
        "active_group_status": extra.get("active_group_status") or "NOT VERIFIED",
        "verification_state": extra.get("active_group_status") or "NOT VERIFIED",
        "approval_status": extra.get("setting_approval") or "NOT VERIFIED",
        "relay_tag": extra.get("relay_tag") or plant.get("relay_tag"),
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

    currents = {
        k: feat.get(k)
        for k in ("Ia", "Ib", "Ic", "I0", "I2", "Ia_elevated", "Ib_elevated", "Ic_elevated")
        if k in feat
    }
    sequences = {
        "I0": feat.get("I0"),
        "I2": feat.get("I2"),
        "ground": feat.get("ground"),
    }
    z_est = feat.get("line_impedance_estimate") if isinstance(feat.get("line_impedance_estimate"), dict) else {}

    return FaultCharacteristicsOut(
        event_id=event.id,
        fault_type=str(fault.fault_type if fault else "UNKNOWN"),
        status=str(fault.status if fault else "UNKNOWN"),
        confidence_level=fault.confidence_level if fault else None,
        involved_phases=fault.involved_phases if fault else None,
        ground_involved=fault.ground_involved if fault else None,
        distance_km=fault.distance_km if fault else None,
        location_method=fault.location_method if fault else None,
        inception_t_us=_first_t("INCEPTION", "FAULT") or (fault.inception_t_us if fault else None),
        pickup_t_us=_first_t("PICKUP"),
        trip_t_us=_first_t("TRIP"),
        clearing_t_us=_first_t("52A", "BREAKER", "CLEAR") or (fault.clearing_t_us if fault else None),
        currents=currents or None,
        sequences=sequences,
        impedance=feat.get("distance_detail") if isinstance(feat.get("distance_detail"), dict) else None,
        location_algorithms=algorithms,
        line_impedance_estimate=z_est or None,
        limitations=limitations,
        explanation=fault.explanation if fault else None,
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
    return RcaResponse(
        event_id=event.id,
        hypotheses=[RcaHypothesisOut.model_validate(r) for r in rows],
        decision_state=event.decision_state,
    )


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
