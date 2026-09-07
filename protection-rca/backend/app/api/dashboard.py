"""Dashboard summary API — engineering operations console."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.dependencies.auth import CurrentUser, DbSession
from app.models import (
    Bay,
    ConsistencyFinding,
    Event,
    FaultClassification,
    ProtectionOperation,
    RcaHypothesis,
    Relay,
    Report,
    Substation,
)
from app.schemas.rules import (
    DashboardAttentionItem,
    DashboardDqBreakdown,
    DashboardRecentEvent,
    DashboardStats,
    DashboardTrendPoint,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


@router.get("/stats", response_model=DashboardStats)
async def dashboard_stats(
    db: DbSession,
    user: CurrentUser,
    days: int = Query(30, ge=7, le=90),
) -> DashboardStats:
    total_events = int(
        (await db.execute(select(func.count()).select_from(Event))).scalar_one() or 0
    )
    awaiting_analysis = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Event)
                .where(Event.status.in_(("UPLOADED", "PARSED", "QUEUED", "ANALYSING")))
            )
        ).scalar_one()
        or 0
    )
    awaiting_review = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Event)
                .where(Event.status.in_(("REVIEW", "AWAITING_REVIEW", "ANALYSED")))
            )
        ).scalar_one()
        or 0
    )
    completed_reports = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Report)
                .where(Report.status.in_(("READY", "PUBLISHED", "COMPLETE", "GENERATED")))
            )
        ).scalar_one()
        or 0
    )
    consistency_issues = int(
        (
            await db.execute(
                select(func.count())
                .select_from(ConsistencyFinding)
                .where(ConsistencyFinding.status == "INCONSISTENT")
            )
        ).scalar_one()
        or 0
    )
    high_severity_findings = int(
        (
            await db.execute(
                select(func.count())
                .select_from(ConsistencyFinding)
                .where(ConsistencyFinding.severity.in_(("HIGH", "CRITICAL")))
            )
        ).scalar_one()
        or 0
    )
    rca_inconclusive = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Event)
                .where(Event.decision_state.in_(("INCONCLUSIVE", "DATA_INSUFFICIENT")))
            )
        ).scalar_one()
        or 0
    )
    parser_dq_issues = int(
        (
            await db.execute(
                select(func.count())
                .select_from(Event)
                .where(Event.data_quality.in_(("WARNING", "POOR", "INVALID")))
            )
        ).scalar_one()
        or 0
    )

    # --- Data quality breakdown ---
    dq_rows = (
        await db.execute(
            select(Event.data_quality, func.count()).group_by(Event.data_quality)
        )
    ).all()
    dq = DashboardDqBreakdown()
    for quality, count in dq_rows:
        c = int(count or 0)
        q = (quality or "").upper()
        if q in ("GOOD",):
            dq.good += c
        elif q in ("ACCEPTABLE",):
            dq.acceptable += c
        elif q in ("WARNING",):
            dq.warning += c
        elif q in ("POOR",):
            dq.poor += c
        elif q in ("INVALID",):
            dq.invalid += c
        elif q in ("NOT_VALIDATED", "NOT VALIDATED"):
            dq.not_validated += c
        elif q in ("UNSUPPORTED",):
            dq.unsupported += c
        else:
            dq.unknown += c
            if not quality:
                dq.not_validated += c
                dq.unknown -= c

    # --- 30-day trend (by created_at day) ---
    now = datetime.now(timezone.utc)
    window = max(7, min(days, 90))
    start = (now - timedelta(days=window - 1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    events_30 = (
        await db.execute(select(Event).where(Event.created_at >= start))
    ).scalars().all()

    buckets: dict[str, dict[str, int]] = {}
    for d in range(window):
        day = (start + timedelta(days=d)).date().isoformat()
        buckets[day] = {"events": 0, "analysed": 0, "review": 0, "issues": 0}

    for e in events_30:
        created = e.created_at
        if created is None:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        day = created.astimezone(timezone.utc).date().isoformat()
        if day not in buckets:
            continue
        buckets[day]["events"] += 1
        status = (e.status or "").upper()
        decision = (e.decision_state or "").upper()
        dqv = (e.data_quality or "").upper()
        if status in ("REVIEW", "AWAITING_REVIEW") or decision == "ENGINEER_REVIEW_REQUIRED":
            buckets[day]["review"] += 1
        elif dqv in ("WARNING", "POOR", "INVALID") or decision in (
            "INCONCLUSIVE",
            "DATA_INSUFFICIENT",
            "UNSUPPORTED_FORMAT",
        ):
            buckets[day]["issues"] += 1
        else:
            buckets[day]["analysed"] += 1

    trend_30d = [
        DashboardTrendPoint(
            date=day,
            events=vals["events"],
            analysed=vals["analysed"],
            review=vals["review"],
            issues=vals["issues"],
        )
        for day, vals in buckets.items()
    ]

    # --- Attention required ---
    attention: list[DashboardAttentionItem] = []
    attention_events = (
        await db.execute(
            select(Event).order_by(Event.updated_at.desc()).limit(40)
        )
    ).scalars().all()
    for e in attention_events:
        reasons: list[tuple[str, str]] = []
        if (e.status or "") in ("UPLOADED", "PARSED", "QUEUED", "ANALYSING"):
            reasons.append(("Awaiting analysis", "MEDIUM"))
        if (e.status or "") in ("REVIEW", "AWAITING_REVIEW", "ANALYSED"):
            reasons.append(("Awaiting engineer review", "HIGH"))
        if (e.decision_state or "") in ("INCONCLUSIVE", "DATA_INSUFFICIENT"):
            reasons.append(("RCA inconclusive / data insufficient", "HIGH"))
        if (e.data_quality or "") in ("WARNING", "POOR", "INVALID"):
            reasons.append((f"Data quality: {e.data_quality}", "HIGH"))
        # consistency high findings count
        hi = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(ConsistencyFinding)
                    .where(
                        ConsistencyFinding.event_id == e.id,
                        ConsistencyFinding.severity.in_(("HIGH", "CRITICAL")),
                    )
                )
            ).scalar_one()
            or 0
        )
        if hi:
            reasons.append((f"{hi} high/critical consistency finding(s)", "CRITICAL"))
        for reason, sev in reasons:
            attention.append(
                DashboardAttentionItem(
                    id=e.id,
                    event_id=e.event_id,
                    reason=reason,
                    severity=sev,
                    href_status=e.status or "",
                )
            )
        if len(attention) >= 8:
            break

    # --- Recent events enriched ---
    recent_rows = (
        await db.execute(select(Event).order_by(Event.created_at.desc()).limit(12))
    ).scalars().all()

    recent_events: list[DashboardRecentEvent] = []
    for e in recent_rows:
        loc = "—"
        if e.substation_id:
            sub = (
                await db.execute(select(Substation).where(Substation.id == e.substation_id))
            ).scalar_one_or_none()
            bay = None
            if e.bay_id:
                bay = (
                    await db.execute(select(Bay).where(Bay.id == e.bay_id))
                ).scalar_one_or_none()
            if sub and bay:
                loc = f"{sub.name} / {bay.name}"
            elif sub:
                loc = sub.name
            elif e.feeder:
                loc = e.feeder
        elif e.feeder:
            loc = e.feeder

        relay_label = "—"
        if e.relay_id:
            rel = (
                await db.execute(select(Relay).where(Relay.id == e.relay_id))
            ).scalar_one_or_none()
            if rel:
                relay_label = rel.relay_tag or rel.name or "—"

        fault = (
            await db.execute(
                select(FaultClassification)
                .where(
                    FaultClassification.event_id == e.id,
                    FaultClassification.is_primary.is_(True),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if fault is None:
            fault = (
                await db.execute(
                    select(FaultClassification)
                    .where(FaultClassification.event_id == e.id)
                    .limit(1)
                )
            ).scalar_one_or_none()

        trips = (
            await db.execute(
                select(ProtectionOperation)
                .where(
                    ProtectionOperation.event_id == e.id,
                    ProtectionOperation.operation_type.in_(("TRIP", "trip", "PICKUP", "pickup")),
                    ProtectionOperation.asserted.is_(True),
                )
                .limit(5)
            )
        ).scalars().all()
        prot = ", ".join(
            sorted({(p.element or p.function_code or "?").strip() for p in trips if p.element or p.function_code})
        ) or "—"

        inconsist = int(
            (
                await db.execute(
                    select(func.count())
                    .select_from(ConsistencyFinding)
                    .where(
                        ConsistencyFinding.event_id == e.id,
                        ConsistencyFinding.status == "INCONSISTENT",
                    )
                )
            ).scalar_one()
            or 0
        )
        cons_summary = f"{inconsist} findings" if inconsist else "Consistent"

        rca = (
            await db.execute(
                select(RcaHypothesis)
                .where(RcaHypothesis.event_id == e.id)
                .order_by(RcaHypothesis.rank.asc())
                .limit(1)
            )
        ).scalar_one_or_none()
        rca_status = (
            (e.decision_state or (rca.status if rca else None) or "—")
        )

        sev = None
        hi_find = (
            await db.execute(
                select(ConsistencyFinding.severity)
                .where(
                    ConsistencyFinding.event_id == e.id,
                    ConsistencyFinding.severity.in_(("CRITICAL", "HIGH", "MEDIUM")),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        if hi_find:
            sev = hi_find

        recent_events.append(
            DashboardRecentEvent(
                id=e.id,
                event_id=e.event_id,
                event_datetime=_iso(e.event_datetime or e.created_at),
                location=loc,
                relay=relay_label,
                fault_type=fault.fault_type if fault else None,
                protection_summary=prot,
                consistency_summary=cons_summary,
                rca_status=str(rca_status),
                severity=sev,
                status=e.status or "",
                data_quality=e.data_quality,
            )
        )

    return DashboardStats(
        total_events=total_events,
        awaiting_analysis=awaiting_analysis,
        awaiting_review=awaiting_review,
        completed_reports=completed_reports,
        consistency_issues=consistency_issues,
        high_severity_findings=high_severity_findings,
        rca_inconclusive=rca_inconclusive,
        parser_dq_issues=parser_dq_issues,
        trend_30d=trend_30d,
        data_quality=dq,
        attention=attention[:8],
        recent_events=recent_events,
    )
