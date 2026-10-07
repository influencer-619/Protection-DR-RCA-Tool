"""Full analysis pipeline orchestrator producing EventAnalysisResult."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional

from anomaly import AnomalyDetector, AnomalyResult
from app.core.enums import BreakerAssessment, JobStage
from audit import AuditService
from comtrade.canonical.model import CanonicalDisturbanceRecord
from consistency import ConsistencyEngine, ConsistencyResult
from decision import DecisionEngine, DecisionResult
from electrical_analysis import ElectricalAnalysisResult, analyze_electrical
from event_reconstruction import TimelineEvent, reconstruct_timeline
from evidence import Evidence, EvidenceGraphBuilder, make_evidence
from fault_analysis import FaultClassificationResult, classify_fault
from fault_analysis.event_class import EventClass
from protection import ProtectionRuleEngine, ProtectionEngineResult
from rca import HypothesisEngine, RCAResult
from reporting import ReportGenerator, ReportBundle
from settings.hierarchy.resolver import SettingRecord, SettingResolution, resolve_setting
from similarity import SimilarityResult, SimilarityService


def _reconcile_event_class_with_rca(
    fault_dict: dict[str, Any],
    *,
    rca: RCAResult,
    electrical_flags: dict[str, Any],
) -> dict[str, Any]:
    """Align DFR event_class with primary RCA for non-fault causes.

    - EVT-18: RCA energization/switching but event_class UNKNOWN
    - EVT-17: RCA motor start but event_class FAULT (V sag + I rise, pickup-only)
    """
    out = dict(fault_dict)
    ec = str(out.get("event_class") or "").upper()

    primary = rca.primary
    hid = str(getattr(primary, "hypothesis_id", "") or "") if primary else ""
    det = electrical_flags.get("detectors") if isinstance(electrical_flags.get("detectors"), dict) else {}
    inrush = det.get("magnetizing_inrush") if isinstance(det, dict) else None
    inrush_ok = electrical_flags.get("magnetizing_inrush") or (
        isinstance(inrush, dict) and str(inrush.get("status") or "").upper() == "POSSIBLE"
    )
    no_trip = not bool(electrical_flags.get("trip_command"))

    new_ec: Optional[str] = None
    if hid == "MOTOR_START" or electrical_flags.get("motor_start"):
        new_ec = EventClass.MOTOR_START
    elif hid == "SWITCHING_TRANSIENT":
        new_ec = EventClass.ENERGIZATION if inrush_ok else EventClass.SWITCHING
    elif inrush_ok and no_trip:
        new_ec = EventClass.ENERGIZATION

    if not new_ec:
        return out

    # Apply when UNKNOWN, or demote false FAULT when no trip + non-fault RCA
    if ec not in (EventClass.UNKNOWN, "", EventClass.FAULT):
        return out
    if ec == EventClass.FAULT and not no_trip:
        return out  # real trip — keep FAULT
    if ec == EventClass.FAULT and new_ec == EventClass.FAULT:
        return out

    out["event_class"] = new_ec
    out["event_class_status"] = "PROBABLE"
    feat = dict(out.get("evidence") or {})
    evc = dict(feat.get("event_classification") or {})
    evc["event_class"] = new_ec
    evc["status"] = "PROBABLE"
    reasons = list(evc.get("reasons") or [])
    reasons.append(f"Aligned with primary RCA ({hid or 'non-fault evidence'})")
    evc["reasons"] = reasons
    feat["event_classification"] = evc
    feat["event_class"] = new_ec
    feat["event_class_status"] = "PROBABLE"
    feat["ground"] = None
    feat["ground_applicable"] = False
    feat["Ia_elevated"] = None
    feat["Ib_elevated"] = None
    feat["Ic_elevated"] = None
    out["evidence"] = feat
    out["fault_type"] = "UNKNOWN"
    out["status"] = "INCONCLUSIVE"
    return out


@dataclass
class EventAnalysisResult:
    event: dict[str, Any]
    data_quality: dict[str, Any]
    comtrade: dict[str, Any]
    electrical_analysis: dict[str, Any]
    timeline: list[dict[str, Any]]
    protection_assessment: list[dict[str, Any]]
    consistency_findings: list[dict[str, Any]]
    fault_classification: dict[str, Any]
    breaker_analysis: dict[str, Any]
    anomalies: dict[str, Any]
    rca_hypotheses: dict[str, Any]
    evidence: list[dict[str, Any]]
    evidence_graph: dict[str, Any]
    similar_events: dict[str, Any]
    decision: dict[str, Any]
    report: dict[str, Any]
    limitations: list[str] = field(default_factory=list)
    setting_reference: dict[str, Any] = field(default_factory=dict)
    stages_completed: list[str] = field(default_factory=list)
    engineer_review: str = "PENDING"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _breaker_from_timeline(timeline: list[TimelineEvent]) -> dict[str, Any]:
    types = {e.event_type for e in timeline}
    has_trip = "protection_trip" in types or "breaker_trip_command" in types
    has_open = "52a_change" in types or "52b_change" in types
    has_interrupt = "current_interruption" in types
    if not has_trip and not has_open and not has_interrupt:
        return {
            "assessment": BreakerAssessment.INCONCLUSIVE.value,
            "reason": "Insufficient breaker evidence",
        }
    if has_trip and has_interrupt:
        return {
            "assessment": BreakerAssessment.NORMAL.value,
            "reason": "Trip and current interruption observed",
        }
    if has_trip and not has_interrupt:
        return {
            "assessment": BreakerAssessment.INCONCLUSIVE.value,
            "reason": "Trip observed but current interruption not confirmed — do not declare failure from one missing signal",
        }
    return {
        "assessment": BreakerAssessment.INCONCLUSIVE.value,
        "reason": "Partial breaker evidence",
    }


class AnalysisPipeline:
    """Runs analysis phases and produces EventAnalysisResult."""

    def __init__(
        self,
        *,
        audit: Optional[AuditService] = None,
        similarity: Optional[SimilarityService] = None,
        anomaly: Optional[AnomalyDetector] = None,
    ) -> None:
        self.audit = audit or AuditService()
        self.similarity = similarity or SimilarityService()
        self.anomaly = anomaly or AnomalyDetector()
        self.protection = ProtectionRuleEngine()
        self.consistency = ConsistencyEngine()
        self.rca = HypothesisEngine()
        self.decision = DecisionEngine()
        self.reporting = ReportGenerator()
        self.evidence_graph = EvidenceGraphBuilder()

    def run(
        self,
        record: CanonicalDisturbanceRecord,
        *,
        event_meta: Optional[dict[str, Any]] = None,
        setting_candidates: Optional[list[SettingRecord]] = None,
        line_params: Optional[dict[str, Any]] = None,
        ct_vt_ratios: Optional[dict[str, Any]] = None,
        relay_settings: Optional[dict[str, Any]] = None,
        extra_timeline: Optional[list[TimelineEvent]] = None,
        user_id: Optional[str] = None,
        unsupported_format: bool = False,
    ) -> EventAnalysisResult:
        event_meta = event_meta or {"event_id": record.record_id}
        event_id = str(event_meta.get("event_id") or record.record_id)
        setting_candidates = setting_candidates or []
        limitations: list[str] = []
        stages: list[str] = []

        self.audit.record(
            action="ANALYSIS_START",
            entity_type="event",
            entity_id=event_id,
            user_id=user_id,
        )

        if unsupported_format:
            decision = self.decision.decide(unsupported_format=True)
            return EventAnalysisResult(
                event=event_meta,
                data_quality={"status": "UNSUPPORTED"},
                comtrade={"record_id": record.record_id},
                electrical_analysis={},
                timeline=[],
                protection_assessment=[],
                consistency_findings=[],
                fault_classification={},
                breaker_analysis={},
                anomalies={"message": "ML RESULT: NOT AVAILABLE"},
                rca_hypotheses={},
                evidence=[],
                evidence_graph={},
                similar_events={"message": "SIMILARITY RESULT: NOT AVAILABLE"},
                decision=decision.to_dict(),
                report={},
                limitations=["Unsupported format"],
                stages_completed=[JobStage.FAILED.value],
            )

        # Signal / electrical
        stages.append(JobStage.SIGNAL_PROCESSING.value)
        channel_map = None
        if isinstance(event_meta.get("channel_map"), dict):
            channel_map = event_meta.get("channel_map")
        elif isinstance(event_meta.get("extra"), dict) and isinstance(
            event_meta["extra"].get("channel_map"), dict
        ):
            channel_map = event_meta["extra"].get("channel_map")
        digital_map = None
        if isinstance(event_meta.get("digital_map"), dict):
            digital_map = event_meta.get("digital_map")
        elif isinstance(event_meta.get("extra"), dict) and isinstance(
            event_meta["extra"].get("digital_map"), dict
        ):
            digital_map = event_meta["extra"].get("digital_map")
        elec = analyze_electrical(record, channel_map=channel_map)
        limitations.extend(elec.limitations)
        # MiCOM / default epoch clocks (1990–1994) are not real event times
        st = getattr(record, "start_time", None)
        if st is not None and getattr(st, "year", None) is not None and 1980 <= int(st.year) <= 1994:
            limitations.append(
                f"DR clock suspect/default ({st.isoformat()}) — do not use as event time"
            )
            q = dict(record.quality or {})
            q["clock_suspect"] = True
            record.quality = q

        if record.samples == 0 and not record.scaled_values:
            decision = self.decision.decide(data_insufficient=True)
            return EventAnalysisResult(
                event=event_meta,
                data_quality=record.quality or {"status": "INSUFFICIENT"},
                comtrade={"record_id": record.record_id, "standard": record.standard},
                electrical_analysis=elec.to_dict(),
                timeline=[],
                protection_assessment=[],
                consistency_findings=[],
                fault_classification={},
                breaker_analysis={},
                anomalies={"message": "ML RESULT: NOT AVAILABLE"},
                rca_hypotheses={},
                evidence=[],
                evidence_graph={},
                similar_events={"message": "SIMILARITY RESULT: NOT AVAILABLE"},
                decision=decision.to_dict(),
                report={},
                limitations=limitations + ["No sample data"],
                stages_completed=stages + [JobStage.FAILED.value],
            )

        # Timeline (COMTRADE + SOE / relay event report)
        stages.append(JobStage.EVENT_RECONSTRUCTION.value)
        timeline = reconstruct_timeline(record, digital_map=digital_map)
        if extra_timeline:
            from app.services.side_files import merge_timelines

            before = len(timeline)
            timeline = merge_timelines(timeline, list(extra_timeline))
            if len(timeline) > before:
                limitations.append(
                    f"Merged {len(timeline) - before} external timeline events from SOE / event report"
                )

        # Settings reference (explicit)
        enabled_res = resolve_setting("enabled", setting_candidates, element="51")
        setting_reference = {
            "setting_source_used": enabled_res.source,
            "setting_version": enabled_res.version,
            "setting_group": enabled_res.group,
            "active_setting_group_verification": enabled_res.verification_status,
            "explanation": enabled_res.explanation,
        }

        # Protection
        stages.append(JobStage.PROTECTION_ANALYSIS.value)
        electrical_flags = {
            "fault_indicated": any(e.event_type == "fault_inception" for e in timeline),
            "current_increase": any(e.event_type == "current_increase" for e in timeline),
            "trip_command": any(
                e.event_type in ("protection_trip", "breaker_trip_command") for e in timeline
            ),
            "current_persists": False,
            "intertrip": any(e.event_type == "intertrip" for e in timeline),
            "channel_roles": dict(elec.channel_roles),
            "phasors": {
                k: (v.to_dict() if hasattr(v, "to_dict") else v) for k, v in elec.phasors.items()
            },
            "detectors": dict(elec.detectors or {}),
        }
        # Optional differential / remote currents from event meta (multi-end)
        multi = event_meta.get("multi_end") or (
            event_meta.get("extra", {}) if isinstance(event_meta.get("extra"), dict) else {}
        ).get("multi_end")
        if isinstance(multi, dict):
            for key in ("i_local", "i_remote", "i_w1", "i_w2", "diff_87", "direction_67", "bf_timing"):
                if key in multi:
                    electrical_flags[key] = multi[key]
        prot = self.protection.assess(
            timeline=timeline,
            setting_candidates=setting_candidates,
            electrical=electrical_flags,
            digital_channel_names=[
                getattr(ch, "name", None) or str(ch)
                for ch in (getattr(record, "digital_channels", None) or [])
            ],
            digital_map=digital_map,
        )
        limitations.extend(prot.limitations)

        # Fault first so consistency severity can use fault context
        stages.append(JobStage.FAULT_CLASSIFICATION.value)
        elec_remote = event_meta.get("elec_remote")  # optional ElectricalAnalysisResult / dict
        sync_offset = None
        if isinstance(multi, dict) and multi.get("sync_offset_us") is not None:
            try:
                sync_offset = float(multi["sync_offset_us"])
            except (TypeError, ValueError):
                sync_offset = None
        fault = classify_fault(
            elec,
            line_params=line_params,
            ct_vt_ratios=ct_vt_ratios,
            relay_settings=relay_settings,
            assessments=prot.assessments,
            elec_remote=elec_remote if hasattr(elec_remote, "phasors") else None,
            sync_offset_us=sync_offset,
            timeline=timeline,
            digital_channel_names=[
                getattr(ch, "name", None) or str(ch)
                for ch in (getattr(record, "digital_channels", None) or [])
            ],
        )
        limitations.extend(fault.limitations)
        if not (fault.evidence or {}).get("distance_applicable"):
            limitations[:] = [
                lim
                for lim in limitations
                if "FAULT DISTANCE" not in lim.upper() and "Z1/KM" not in lim.upper()
            ]

        # Consistency (severity adjusted by fault type / zone)
        stages.append(JobStage.CONSISTENCY_CHECKER.value)
        cons = self.consistency.run(
            event_id=event_id,
            assessments=prot.assessments,
            timeline=[e.to_dict() for e in timeline],
            fault_type=fault.fault_type,
            fault_status=fault.status,
        )

        breaker = _breaker_from_timeline(timeline)

        # Anomaly / ML
        anom = self.anomaly.analyze(None)

        # Similarity
        sim = self.similarity.find_similar(event_id=event_id)

        # IEEE/PSRC DFR event class → RCA electrical flags (gate before fault typing)
        ec = fault.event_class
        ecs = fault.event_class_status
        if not ec:
            ec_feat = (fault.evidence or {}).get("event_classification")
            if isinstance(ec_feat, dict):
                ec = ec_feat.get("event_class")
                ecs = ecs or ec_feat.get("status")
        if ec:
            electrical_flags["event_class"] = str(ec)
            if ecs:
                electrical_flags["event_class_status"] = str(ecs)
            if str(ec) != "FAULT":
                electrical_flags["no_fault"] = True
                electrical_flags["fault_indicated"] = False
                if str(ec) == "ENERGIZATION":
                    electrical_flags["magnetizing_inrush"] = True
                    electrical_flags["switching_correlated"] = True
                elif str(ec) == "MOTOR_START":
                    electrical_flags["motor_start"] = True
                    electrical_flags["switching_correlated"] = True
                elif str(ec) == "SWITCHING":
                    electrical_flags["switching_correlated"] = True

        # Enrich electrical flags from fault evidence before RCA (available-data scoring)
        if str(ec or "") == "FAULT" and fault.status in ("CLASSIFIED", "PROBABLE"):
            electrical_flags["fault_indicated"] = True
            feat = fault.evidence if isinstance(fault.evidence, dict) else {}
            if feat.get("available") or any(
                feat.get(k)
                for k in ("Ia_elevated", "Ib_elevated", "Ic_elevated", "ground")
            ):
                electrical_flags["current_increase"] = True
            if feat.get("ground"):
                electrical_flags["ground_involved"] = True

        # Scheme library + cause enrichment (deterministic)
        from protection.schemes import detect_schemes, primary_scheme, scheme_tokens
        from rca.enrichment import collect_enrichment_tokens

        operated_els = [
            str(a.element)
            for a in prot.assessments
            if a.pickup is True
            or a.trip is True
            or str(a.actual_operation or "").upper() == "OPERATED"
        ]
        enabled_els = [
            str(a.element)
            for a in prot.assessments
            if a.enabled is True
        ]
        digital_roles: list[str] = []
        for ev in timeline:
            meta = ev.metadata if isinstance(getattr(ev, "metadata", None), dict) else {}
            role = meta.get("target_role")
            if role:
                digital_roles.append(str(role).upper())
            if ev.event_type == "communication_signal":
                digital_roles.append("COMM")
            if ev.event_type == "intertrip":
                digital_roles.append("INTERTRIP")
        scheme_matches = detect_schemes(
            operated_elements=operated_els,
            enabled_elements=enabled_els,
            digital_roles=digital_roles,
        )
        top_scheme = primary_scheme(scheme_matches)
        sch_toks = scheme_tokens(scheme_matches)
        electrical_flags["scheme_tokens"] = sorted(sch_toks)
        if top_scheme:
            electrical_flags["scheme_id"] = top_scheme.scheme_id
            electrical_flags["scheme_label"] = top_scheme.label
            electrical_flags["scheme_zone"] = top_scheme.zone

        tl_types = [getattr(ev, "event_type", "") for ev in timeline]
        if "communication_signal" in tl_types:
            electrical_flags["comm_channel"] = True
        if "intertrip" in tl_types:
            electrical_flags["intertrip"] = True
        if "reclose" in tl_types:
            electrical_flags["switching_correlated"] = True
        # Breaker status change → close/open context for switch-onto-fault RCA
        if "52a_change" in tl_types or "52b_change" in tl_types:
            electrical_flags["breaker_close"] = True
            electrical_flags["switching_correlated"] = True
        electrical_flags["timeline_event_types"] = sorted({str(t) for t in tl_types if t})

        electrical_flags["digital_channel_names"] = [
            getattr(ch, "name", None) or str(ch)
            for ch in (getattr(record, "digital_channels", None) or [])
        ]

        extra = event_meta.get("extra") if isinstance(event_meta.get("extra"), dict) else {}
        cause_ev = event_meta.get("cause_evidence")
        if cause_ev is None:
            cause_ev = extra.get("cause_evidence")
        asset_type = event_meta.get("asset_type") or extra.get("asset_type")
        asset_name = event_meta.get("asset_name") or extra.get("asset_name")
        lightning_csv = event_meta.get("lightning_csv") or extra.get("lightning_csv")
        event_time = event_meta.get("event_datetime") or extra.get("event_datetime")
        enrich_toks, enrich_lims, enrich_detail = collect_enrichment_tokens(
            cause_evidence=cause_ev,
            asset_type=str(asset_type) if asset_type else None,
            asset_name=str(asset_name) if asset_name else None,
            timeline_event_types=tl_types,
            lightning_csv=lightning_csv,
            event_time=event_time if hasattr(event_time, "isoformat") else None,
        )
        limitations.extend(enrich_lims)

        # RCA — score hypotheses from whatever evidence is available
        stages.append(JobStage.RCA.value)
        rca = self.rca.run(
            fault=fault,
            assessments=prot.assessments,
            consistency=cons,
            electrical_flags=electrical_flags,
            ml_available=anom.status == "OK",
            similarity_available=sim.status == "OK",
            extra_evidence=enrich_toks,
            enrichment_detail=enrich_detail,
            scheme_detail={
                "primary": top_scheme.to_dict() if top_scheme else None,
                "matches": [m.to_dict() for m in scheme_matches[:5]],
            },
        )
        limitations.extend(rca.limitations)

        # Align event_class with RCA when DFR gate stayed UNKNOWN (e.g. EVT-18)
        fault_dict = _reconcile_event_class_with_rca(
            fault.to_dict(),
            rca=rca,
            electrical_flags=electrical_flags,
        )

        # Evidence
        stages.append(JobStage.EVIDENCE.value)
        evidence_items: list[Evidence] = []
        for name, sr in list(elec.rms.items())[:6]:
            evidence_items.append(
                make_evidence(
                    source_type="CALCULATION",
                    source_id=record.record_id,
                    parameter=f"rms:{name}",
                    value=sr.value,
                    unit=sr.unit,
                    interpretation=f"status={sr.status}",
                    confidence="MEDIUM" if sr.status == "OK" else "INCONCLUSIVE",
                    timestamp=sr.timestamp,
                )
            )
        for f in cons.findings:
            evidence_items.append(
                make_evidence(
                    source_type="PROTECTION_RULE",
                    source_id=f.finding_id,
                    parameter=f.check_type,
                    value=f.observed,
                    expected=f.expected,
                    observed=f.observed,
                    interpretation=f.explanation,
                    confidence=f.confidence,
                )
            )

        graph = self.evidence_graph.build(
            rca_primary_id=(rca.primary.hypothesis_id if rca.primary else "UNKNOWN"),
            hypotheses=[h.to_dict() for h in rca.hypotheses],
            findings=[f.to_dict() for f in cons.findings],
            calculations=evidence_items[:10],
            source_files=list(record.source_files),
        )

        decision = self.decision.decide(
            consistency=cons,
            rca=rca,
            warnings=limitations[:5],
        )

        # Report
        stages.append(JobStage.REPORT.value)
        analysis_dict = {
            "event": event_meta,
            "data_quality": record.quality or {},
            "electrical_analysis": elec.to_dict(),
            "timeline": [e.to_dict() for e in timeline],
            "protection_assessment": [a.to_dict() for a in prot.assessments],
            "consistency_findings": [f.to_dict() for f in cons.findings],
            "fault_classification": fault_dict,
            "breaker_analysis": breaker,
            "rca_hypotheses": rca.to_dict(),
            "evidence": [e.to_dict() for e in evidence_items],
            "similar_events": sim.to_dict(),
            "decision": decision.to_dict(),
            "limitations": limitations,
            "setting_reference": setting_reference,
            "engineer_review": "PENDING",
        }
        report = self.reporting.render(analysis_dict)

        stages.append(JobStage.COMPLETE.value)
        self.audit.record(
            action="ANALYSIS_COMPLETE",
            entity_type="event",
            entity_id=event_id,
            user_id=user_id,
            details={"decision": decision.state},
        )

        return EventAnalysisResult(
            event=event_meta,
            data_quality=record.quality or {},
            comtrade={
                "record_id": record.record_id,
                "standard": record.standard,
                "revision": record.revision,
                "samples": record.samples,
            },
            electrical_analysis=elec.to_dict(),
            timeline=[e.to_dict() for e in timeline],
            protection_assessment=[a.to_dict() for a in prot.assessments],
            consistency_findings=[f.to_dict() for f in cons.findings],
            fault_classification=fault_dict,
            breaker_analysis=breaker,
            anomalies=anom.to_dict(),
            rca_hypotheses=rca.to_dict(),
            evidence=[e.to_dict() for e in evidence_items],
            evidence_graph=graph.to_dict(),
            similar_events=sim.to_dict(),
            decision=decision.to_dict(),
            report={
                "html": report.html,
                "statements": [
                    {"kind": s.kind, "text": s.text, "section": s.section}
                    for s in report.statements
                ],
                "template_version": report.template_version,
            },
            limitations=limitations,
            setting_reference=setting_reference,
            stages_completed=stages,
        )
