# Implementation log

Track stage exits from [`GAP_ANALYSIS_AND_ROADMAP.md`](GAP_ANALYSIS_AND_ROADMAP.md).

| Stage | Completed | Notes |
|-------|-----------|-------|
| A — Stabilize engineering core | 2026-10-09 | GAP-TEST-001 / ENG-002 / ENG-003. RCA ANSI longest-token expand; classify AG/ABC when DFR class is UNKNOWN (suppress only ENERGIZATION/MOTOR_START/SWITCHING/DISTURBANCE); `fault_classified` without requiring `event_class==FAULT`. Full backend pytest: 395 passed, 2 skipped. |
| B — Job & packaging reliability | 2026-10-09 | GAP-REL-008 / REL-009. `schedule_deferred_job` + BackgroundTasks after commit; orphan PENDING re-kicks once then fails; heal never touches RUNNING; `age_seconds` on AnalysisJobOut; `aiosqlite` in requirements; README plant-first + IMPLEMENTATION_STATUS aligned. |
| C — Matrix + compound LBB | 2026-10-09 | GAP-RCA-004 / RCA-005. Expanded to **full 54-row Excel pack** (`matrix_v1` v1.1.0) + LBB 10-step + bus guardrail; `prefer_primary`; new hyps (HIF, motor jam/locked rotor, overflux, capacitor, …); source xlsx under `docs/reference/`. |
| D — Dual-terminal line | 2026-10-09 | GAP-ENG-007 / UX-010. `electrical_analysis.dual_end_87l`; engineering_persist wires LOCAL+REMOTE phasor compare into `multi_end.dual_end_87l` / `diff_87`; one-end → INCOMPLETE; RMS-only does not claim operate. UI: Local/Remote blurbs honest; CreateEvent/Upload orphan pages deleted. |
| E — Incident correlation | 2026-10-09 | GAP-DATA-006 / DATA-011. `Incident` + `IncidentMember` models; `/api/incidents` create/link/unlink/attach-late/by-event; combined analysis creates parent incident with explicit COMBINED_* reason; TIMESTAMP_ONLY rejected. RCA hypotheses + report_analysis carry matrix/engine versions; `analysis_history` keeps prior job ids on re-run. |
| F — Hardening | 2026-10-09 | GAP-SEC-012 / PERF-013 / ML-014. `secret_redaction` in `write_audit`; SECURITY Stage F checklist + encryption-at-rest guidance; `PERFORMANCE.md` + `WAVEFORM_MAX_POINTS` / `WAVEFORM_MAX_CHANNELS`; RCA `supporting_scores` + RcaPage unavailable banner; tests `test_secret_redaction`, `test_ml_honesty`, `test_waveform_perf_caps`. |
| Combined RCA removal | 2026-10-09 | Product path removed: sidebar Combined RCA, `/analysis/*` pages, `POST /combined-analysis`, `combined_analysis` / `peer_analysis` / `dual_end_87l`, combined UI chrome. Excel `matrix_v1` LBB evidence scoring retained on single-IED events. Manual Incident APIs kept. |
