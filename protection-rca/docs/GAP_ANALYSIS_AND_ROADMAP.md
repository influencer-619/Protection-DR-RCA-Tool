# GAP ANALYSIS AND ROADMAP

**Based on:** [`CURRENT_STATE_AUDIT.md`](CURRENT_STATE_AUDIT.md) (2026-10-09)  
**External engineering reference:** `Complete_Generalized_Protection_RCA_Matrix_L1_L2_L3_Fallback_LBB.xlsx`  
**Principle:** Extend the existing app — no rewrite, no duplicate Cascade/Line tabs, no second RCA engine.

---

## 1. Phase Two evaluation summary

| Dimension | Verdict | Highest-impact issues |
|-----------|---------|------------------------|
| Functional completeness | Strong core; weak multi-IED incident model | No parent Incident; combined = new Event copy |
| Engineering correctness | Solid COMTRADE/protection path; RCA/fault regressions | 11 failing tests; ANSI phrasing breaks earth-code statements; matrix not executable |
| Data integrity | Good file immutability; weak disturbance identity | Duplicate/late peer handling is manual |
| Usability | Plant-first + event tabs work | Stale docs; orphan Create/Upload pages; Local/Remote naming vs “line differential” |
| Security / reliability | No OT write; JWT roles | Orphan analysis jobs (partially healed); `aiosqlite` not in requirements |

**Test baseline:** `401 passed, 11 failed, 1 skipped` (`backend/tests/`, 2026-10-09).

---

## 2. Priority order (master-prompt ranking)

1. Misleading engineering conclusions / broken RCA–fault tests  
2. Data loss, job orphaning, packaging deps  
3. Broken core analyse workflows  
4. Incorrect protection / cascade interpretation  
5. Missing essential RCA (L1/L2/L3 matrix, compound LBB)  
6. Usability / documentation  
7. Performance  
8. Advanced analytics (ML, pgvector)

---

## 3. Gap register

### GAP-TEST-001 — Failing RCA / decision / fault classification tests

| Field | Content |
|-------|---------|
| Capability | RCA scoring, decision state, fault type AG/ABC |
| Current | 11 pytest failures: `test_decision`, `test_rca`, `test_fault_classification`, `test_inrush_charging_framing` |
| Expected | Suite green; CONFIRMED/PROBABLE/POSSIBLE and AG/ABC classifications match intended rules |
| Class | Defective |
| Impact | Engineering credibility; CI cannot gate releases |
| Severity | **Critical** |
| Dependencies | `backend/rca/`, `fault_analysis/`, `decision/` |
| Solution | Fix root causes (not blanket test weakening); restore fault typing; align decision downgrade rules |
| Acceptance | Targeted modules + full `pytest tests/ -q` pass (or documented waivers only for env-specific cases) |
| Regression | Existing cascade BF path; combined analysis |

---

### GAP-ENG-002 — ANSI technical names break element codes in RCA statements

| Field | Content |
|-------|---------|
| Capability | RCA narrative phrasing for 50N/51N/etc. |
| Current | Statements show fragments like `51 (time overcurrent)n` / `50 (Instantaneous overcurrent)N`; tests expect `51n` / `50N` |
| Expected | `format_ansi("51N")` → `51N (Neutral / earth time overcurrent)`; never split base number from suffix letter |
| Class | Defective |
| Impact | Misleading reports/UI; false “wrong element” reading |
| Severity | **Critical** |
| Dependencies | `protection/ansi_names.py`, RCA statement builders, report filters |
| Solution | Apply `format_ansi` only to whole element tokens; longest-match when scanning phrases; fix call sites that format `50` before `50N` |
| Acceptance | `test_inrush_charging_framing` earth-fault narrative tests pass; spot-check report HTML |
| Regression | UI compact ANSI display; report `ansi_label` filter |

---

### GAP-ENG-003 — Fault classifier returns UNKNOWN for classic AG/ABC fixtures

| Field | Content |
|-------|---------|
| Capability | Fault type classification |
| Current | `test_classify_ag` / `test_classify_abc` → `fault_type='UNKNOWN'` |
| Expected | AG / ABC (or ABCG) with CLASSIFIED when synthetic evidence supports |
| Class | Defective |
| Impact | Downstream RCA cannot confirm zone faults (`fault_classified` token) |
| Severity | **Critical** |
| Dependencies | `fault_analysis/` |
| Solution | Debug classifier regression (thresholds, event_class gate, ground logic); add fixture assertion with evidence dump |
| Acceptance | Those two tests pass; golden COMTRADE AG/ABC still sane |
| Regression | DFR non-fault classes (motor start, switching) |

---

### GAP-RCA-004 — Excel L1/L2/L3/LBB matrix not executed by the engine

| Field | Content |
|-------|---------|
| Capability | Vendor-neutral scenario matrix with fallbacks |
| Current | ~22 hypotheses in `rules/rca/hypotheses.yaml`; matrix has ~54 scenarios + LBB 10-step + fallback methodology |
| Expected | Versioned, machine-readable scenarios that `HypothesisEngine` (or a thin adapter) executes; L1/L2/L3/fallback explicit on each conclusion |
| Class | Missing |
| Impact | Incomplete coverage (motor jam, HIF, overflux, capacitor, compound LBB taxonomy) |
| Severity | **High** |
| Dependencies | GAP-TEST-001; keep single engine |
| Solution | Import matrix → YAML/JSON scenario pack (`rules/rca/matrix_v1.yaml`); map to evidence tokens; extend engine for multi-label compound outcomes without forking engines |
| Acceptance | At least LBB cascade + feeder in-zone + transformer through-fault + inrush fallbacks driven from matrix rows with traces |
| Regression | Existing hypothesis IDs remain stable or aliased |

---

### GAP-RCA-005 — Compound LBB classification not first-class

| Field | Content |
|-------|---------|
| Capability | “Fault + local BF + backup clearing” as structured RCA |
| Current | Separate `BREAKER_FAILURE` / `INTERTRIP_OPERATION` / feeder fault hyps; cascade notes narrative |
| Expected | Matrix-style final class e.g. `FAULT + LOCAL BREAKER FAILURE + LBB/CASCADE CLEARING` with step evidence (Excel LBB sheet steps 1–10) |
| Class | Partial |
| Impact | Cascade events under-explained; risk of “bus fault” misread |
| Severity | **High** |
| Dependencies | GAP-RCA-004; `cascade_lbb.py`; combined events |
| Solution | Add compound outcome object on event/RCA payload; UI Summary/RCA show initiating fault vs BF vs backup; enforce “no bus fault without bus evidence” |
| Acceptance | LV/HV LBB sample shows compound class + step checklist; bus hyp UNLIKELY without 87B evidence |
| Regression | Existing BREAKER_FAILURE CONFIRMED path |

---

### GAP-DATA-006 — No parent Incident entity / correlation

| Field | Content |
|-------|---------|
| Capability | Multi-IED parent incident |
| Current | Combined analysis creates a **new Event** copying files; no Incident table |
| Expected | Parent incident linking original IED events; local RCA retained; late DR can attach |
| Class | Missing |
| Impact | Operational multi-IED workflow; duplicates; no merge/split |
| Severity | **High** (after Critical engineering fixes) |
| Dependencies | Clear correlation rules; do not time-window-merge blindly |
| Solution | New `Incident` model + APIs; combined UI can create/link incident; keep combined Event as one implementation option during transition |
| Acceptance | Two source events link to one incident; unlink/split supported; correlation reason stored |
| Regression | Cascade/Local-Remote combined event creation must keep working |

---

### GAP-ENG-007 — Line multi-end lacks verified dual-terminal 87L comparison

| Field | Content |
|-------|---------|
| Capability | Line differential multi-terminal analysis |
| Current | LOCAL/REMOTE packaging + sync/overlay UI; 87L mostly digital/token based |
| Expected | When both ends have valid I/V, polarity, CT ratios, time alignment → operate/restraint (or explicit incomplete) |
| Class | Partial |
| Impact | “Line differential” label oversells capability |
| Severity | **High** |
| Dependencies | Channel maps, CT/VT, sync offset, GAP-ENG-002 |
| Solution | Extend electrical/protection path for dual-end current comparison; UI shows completeness; never claim internal/external without data |
| Acceptance | Synthetic two-terminal internal vs external cases; one-terminal → incomplete combined assessment |
| Regression | Cascade LBB path unchanged |

---

### GAP-REL-008 — Analysis job queue reliability

| Field | Content |
|-------|---------|
| Capability | Background analyse completion |
| Current | FastAPI BackgroundTasks + orphan heal/re-kick; Celery optional |
| Expected | Deterministic start; no sticky ANALYZING; portable EXE reliable |
| Class | Partial / defective historically |
| Impact | Cascade appears “stuck”; user blocked |
| Severity | **High** |
| Dependencies | `analysis_service.py`, launcher |
| Solution | Harden claim/commit; consider always `asyncio.create_task` after commit; document Celery vs sync; add job age metrics |
| Acceptance | Forced re-run on combined event completes without manual DB edit; heal does not kill live RUNNING jobs |
| Regression | Sync `defer=False` path |

---

### GAP-REL-009 — Packaging / dependency drift

| Field | Content |
|-------|---------|
| Capability | Local SQLite + EXE build |
| Current | `.env` uses aiosqlite; not in `requirements.txt`; README stale routes |
| Expected | Declared deps install cleanly; docs match plant-first UX |
| Class | Defective / usability |
| Impact | New env / portable build breaks |
| Severity | **Medium** |
| Dependencies | requirements, README, IMPLEMENTATION_STATUS |
| Solution | Add `aiosqlite`; refresh README + IMPLEMENTATION_STATUS from audit |
| Acceptance | Fresh venv `pip install -r requirements.txt` runs app on SQLite |
| Regression | Postgres compose path |

---

### GAP-UX-010 — Orphan pages and naming clarity

| Field | Content |
|-------|---------|
| Capability | Navigation honesty |
| Current | `CreateEventPage` / `UploadPage` unrouted; Local/Remote blurb says differential |
| Expected | Dead code removed or reconnected; naming matches capability (or capability upgraded per GAP-ENG-007) |
| Class | Usability |
| Severity | **Medium** |
| Solution | Delete or wire orphans; subtitle “Local / Remote dual-end” until 87L compare ships |
| Acceptance | No redirect stubs claiming wizards that do not exist |
| Regression | Plant → IED upload remains primary |

---

### GAP-DATA-011 — Late-arriving / reprocess versioning

| Field | Content |
|-------|---------|
| Capability | Reproducible historical RCA |
| Current | Re-run overwrites artefacts; limited rule-version stamp on conclusions |
| Expected | Rule/engine version on RCA; optional prior snapshot; config changes audited |
| Class | Partial |
| Severity | **Medium** |
| Solution | Persist `engine_version` / matrix version on hypotheses; report footer already partial — extend |
| Acceptance | Report shows rule version; re-run creates new job id linked on event |
| Regression | Report download |

---

### GAP-SEC-012 — Credential & upload hardening review

| Field | Content |
|-------|---------|
| Capability | IED passwords, upload bounds |
| Current | Metadata stores IEC settings; size limits exist |
| Expected | Documented encryption-at-rest or OS secret store guidance; no secrets in logs |
| Class | Partial / unverified |
| Severity | **Medium** |
| Solution | Audit log redaction; secrets not in API responses; confirm limits |
| Acceptance | Grep/logs review checklist in TEST report |
| Regression | IEC fetch still works |

---

### GAP-PERF-013 — Large waveform UX / memory

| Field | Content |
|-------|---------|
| Capability | Dual-end DR for long records |
| Current | Sample cache + channel cap tests exist |
| Expected | Predictable performance for dual overlay |
| Class | Performance |
| Severity | **Low** |
| Solution | Keep caps; lazy load remote; document limits |
| Acceptance | Cap tests remain green |
| Regression | Waveform accuracy |

---

### GAP-ML-014 — ML / similarity optional path

| Field | Content |
|-------|---------|
| Capability | Supporting scores |
| Current | Weights exist; often NOT AVAILABLE |
| Expected | Explicit “unavailable” in UI; no fake confidence |
| Class | Partial |
| Severity | **Low** |
| Solution | Surface availability flags; do not block deterministic RCA |
| Acceptance | RCA works with ml weight = 0 |
| Regression | Deterministic scores |

---

## 4. Implementation roadmap (stages)

### Stage A — Stabilize engineering core (Critical)  
**Gaps:** TEST-001, ENG-002, ENG-003  
**Exit:** Full pytest green (or ≤0 unexpected fails); ANSI statements correct; AG/ABC classification restored.

### Stage B — Job & packaging reliability  
**Gaps:** REL-008, REL-009  
**Exit:** Combined analyse reliable on EXE/SQLite; requirements complete; docs aligned.

### Stage C — Matrix-driven RCA + compound LBB (extend existing engine)  
**Gaps:** RCA-004, RCA-005  
**Exit:** Versioned matrix pack executed; cascade Summary shows compound class + LBB steps; bus-fault guardrail.

### Stage D — Dual-terminal line assessment  
**Gaps:** ENG-007, UX-010 (naming)  
**Exit:** Completeness-aware 87L/dual-end electrical compare when data allows; honest UI labels.

### Stage E — Parent incident correlation  
**Gaps:** DATA-006, DATA-011  
**Exit:** Incident model + link/unlink; late DR attach; no timestamp-only merge.

### Stage F — Hardening & polish  
**Gaps:** SEC-012, PERF-013, ML-014  
**Exit:** Security checklist, performance notes, ML honesty. **Done** — see `SECURITY.md`, `PERFORMANCE.md`, RCA `supporting_scores`.

---

## 5. Explicit non-goals (this program)

- Full rewrite of frontend or backend  
- Second Cascade/LBB or Line Diff tab  
- Second RCA engine alongside `HypothesisEngine`  
- Generative AI conclusions  
- OT control / trip commands  
- Claiming field validation from synthetic-only tests  

---

## 6. Dependency graph

```text
A (tests + ANSI + fault type)
 └─► B (jobs + packaging)
      └─► C (matrix + compound LBB)
           ├─► D (true line dual-terminal)
           └─► E (Incident correlation)
                └─► F (security/perf/ML polish)
```

---

## 7. Immediate next implementation step

**Start Stage A:**  
1. Fix ANSI whole-token formatting in RCA statements (GAP-ENG-002) — likely unblocks inrush framing tests.  
2. Repair fault AG/ABC classification (GAP-ENG-003).  
3. Reconcile decision/RCA confidence tests (GAP-TEST-001).  

After Stage A is green, proceed to Stage B then C (matrix), which is the highest product value aligned with the Excel LBB/fallback methodology.

---

## 8. Acceptance tracking

| Stage | Status | Notes |
|-------|--------|-------|
| A | **Complete** | ANSI whole-token; AG/ABC + UNKNOWN event_class; RCA fault_classified; pytest green |
| B | **Complete** | Dual-schedule analyse; orphan re-kick then fail; heal skips RUNNING; aiosqlite + README |
| C | **Complete** | Full Excel pack: `matrix_v1.yaml` **v1.1.0 / 54 scenarios** + MatrixMatcher; compound LBB 10-step; bus guardrail; Summary UI |
| D | **Complete** | Dual-end 87L completeness-aware compare; honest Local/Remote labels; orphan Create/Upload pages removed |
| E | **Complete** | Incident + IncidentMember; link/unlink/late-attach APIs; combined creates incident; no timestamp-only merge; RCA/job version stamps |
| F | **Complete** | Audit secret redaction; SECURITY checklist; PERFORMANCE.md + configurable waveform caps; RCA supporting_scores + UI honesty |

Update this table in `IMPLEMENTATION_LOG.md` when stages complete.

---

*Stages A–F implemented in-session after Phase Two/Three audit.*
