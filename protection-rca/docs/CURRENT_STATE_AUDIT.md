# CURRENT STATE AUDIT

**Product:** Protection Expert System / Protection RCA (IEC 61850)  
**Audit scope:** `protection-rca/` repository (backend, frontend, rules, portable packaging)  
**Audit date:** 2026-10-09  
**Method:** Source inspection, API/route inventory, model review, pytest baseline — **not** a field validation against live IEDs.

**Related external reference (not yet wired into code):**  
`Complete_Generalized_Protection_RCA_Matrix_L1_L2_L3_Fallback_LBB.xlsx` (L1 relay / L2 SOE / L3 DR + LBB cascade methodology).

---

## 1. Executive summary

This is a **working, multi-module disturbance-record analysis webapp** with:

- Plant hierarchy → IED workspace → event analysis tabs
- COMTRADE ingest, waveform/DR workspace, protection assessment, consistency, RCA, report, review
- Dual-end **Cascade/LBB** and **Local/Remote (LINE_MULTI_END)** combined-event creation
- IEC 61850 browse/fetch + optional auto-fetch
- Portable EXE packaging

It is **not** yet a full multi-IED **parent-incident** correlation platform. There is **no `Incident` entity**. Combined analysis creates a **new Event** that copies files from two source events. Line “differential” UI is primarily **dual-end packaging + scheme-aware RCA tokens**, not a verified multi-terminal I_diff / I_restraint engine comparable to SIGRA dual-end differential analysis.

**Baseline tests (2026-10-09):** `401 passed, 11 failed, 1 skipped` in `backend/tests/`. Failures are pre-existing relative to this audit pass (decision/RCA/fault framing assertions) — treat as **known defective / unverified** until fixed.

---

## 2. Technology stack (verified)

### 2.1 Frontend (`protection-rca/frontend`)

| Item | Evidence |
|------|----------|
| React 18 + TypeScript + Vite 6 | `frontend/package.json` |
| react-router-dom 7 | `App.tsx` route tree |
| Zustand (auth, theme) | `stores/authStore.ts`, `stores/themeStore.ts` |
| Event workspace Context | `context/EventWorkspaceContext.tsx` |
| Axios API client | `services/api.ts` |
| Vitest | `package.json` scripts |
| Dev proxy `/api` → `:8001` | `vite.config.ts` |

### 2.2 Backend (`protection-rca/backend`)

| Item | Evidence |
|------|----------|
| FastAPI 0.115 + Uvicorn | `requirements.txt`, `app/main.py` |
| SQLAlchemy 2 async | `app/database.py` |
| Dual DB: plant/events + auth | `Base` / `AuthBase`, `DATABASE_URL` / `AUTH_DATABASE_URL` |
| Alembic present (initial) | `alembic/versions/0001_initial_schema.py` |
| Runtime `create_all` + SQLite column patches | `app/database.py` |
| Celery task exists; analyse usually BackgroundTasks | `workers/`, `app/api/analysis.py` (`defer=True`) |
| Local file storage | `LOCAL_STORAGE_PATH` / `storage/` |
| COMTRADE package in-repo | `backend/comtrade/` |
| Optional `pyiec61850-ng` | IEC 61850 client |

### 2.3 Packaging / deploy

- Local: `scripts/start-all.bat`, `ProtectionRCA.exe` + `_internal`
- Portable: `scripts/build-portable-share.bat` → `portable-share/`
- Docker Compose: postgres, redis, minio, backend, worker, frontend (`docker-compose.yml`)

### 2.4 Stack gaps

| Gap | Evidence |
|-----|----------|
| `aiosqlite` used via SQLite URL but not listed in `requirements.txt` | `.env` + requirements |
| README still says guided `/events/new`; router redirects to `/plant` | `README.md` vs `App.tsx` |
| Empty dirs `backend/database/`, `backend/ingestion/` | filesystem |
| Auth DB separate from plant DB — user IDs are strings, no FK | models |

---

## 3. Domain model (verified)

### 3.1 Hierarchy

```
Substation → VoltageLevel → Bay → Feeder → Relay (IED)
                              ↘ Asset, Breaker
Event → EventFile → ComtradeFile → ComtradeChannel → Measurement
Event → EventTimeline, ProtectionOperation, ConsistencyFinding,
        FaultClassification, RcaHypothesis, Evidence, Report,
        EngineerReview, AnalysisJob
```

**Peer topology (configuration):** stored largely in `Relay.metadata_json` (`remote_peer.py`: `peer_type` = `line_remote` | `cascade`, `cascade_role`, `remote_relay_id`) — **not** a first-class topology graph of breakers/zones.

### 3.2 Missing vs master-prompt target

| Concept | Status |
|---------|--------|
| Parent **Incident** with linked IED DRs | **Missing** (no model/API) |
| Versioned scenario matrix (L1/L2/L3 Excel) as executable rules | **Missing** (RCA uses `rules/rca/hypotheses.yaml` + Python) |
| Explicit observed vs inferred event typing in persistence | **Partial** (timeline/RCA statements; not a first-class evidence-class enum everywhere) |
| Compound RCA label e.g. “fault + BF + LBB clearing” as structured fields | **Partial** (hypothesis IDs + cascade notes; not matrix taxonomy) |

---

## 4. Navigation & UI inventory

### 4.1 Global

| Route | Page | Status |
|-------|------|--------|
| `/plant` | Plant hierarchy CRUD | Implemented (API-backed) |
| `/plant/ieds/:iedId` | IED acquire (IEC61850 + upload) | Implemented |
| `/analysis/cascade` | CombinedAnalysisPage (CASCADE_LBB) | Implemented |
| `/analysis/local-remote` | CombinedAnalysisPage (LINE_MULTI_END) | Implemented |
| `/analysis/line` | Redirect → local-remote | Implemented |
| `/dashboard` | Ops dashboard | Implemented |
| `/events` | Global event list | Implemented |
| `/events/compare` | Compare two events | Implemented |
| `/users`, `/audit`, `/help` | Admin / guide | Implemented |
| `/events/new`, `/upload` | Redirect → `/plant` | **Orphan pages remain** (`CreateEventPage`, `UploadPage` unused) |

### 4.2 Event workspace tabs (`EventLayout`)

Setup / Analyse / Protect / Conclude groups covering: overview, summary, files, comtrade, channel-map, digital-map, DR, waveforms, timeline, electrical, fault-*, protection, consistency, RCA, evidence, report, review.

Combined events get `CombinedModeStrip`, dual-end DR/waveforms, cascade sequence panel.

### 4.3 Cascade vs Line Differential tabs

**Fact:** Two sidebar entries, **one shared page component** (`CombinedAnalysisPage`), mode from pathname.  
**Naming:** UI says “Local / Remote”, not “Line Differential”; API mode `LINE_MULTI_END`.  
**Preserve rule:** Do not create a second Cascade or Line Diff configuration system — extend these.

---

## 5. Critical workflow traces

### 5.1 Plant → IED → DR (manual)

1. UI: Plant CRUD → Open IED  
2. Upload files on IED workspace (creates/links event under that relay)  
3. Files stored with SHA-256; analysis job via `/api/analyse`  
4. Pipeline: COMTRADE ingest → `persist_engineering_analysis` → artefacts on Event  

**Status:** Implemented and largely verified by feature use + tests (`test_pipeline_integration`, COMTRADE tests).  
**Caveat:** Channel mapping quality gates RCA accuracy.

### 5.2 Automatic DR retrieval (IEC 61850)

1. IED connection config in relay metadata  
2. Browse/fetch API; auto-fetch scheduler in app lifespan (`auto_fetch.py`, ~30 s tick)  
3. Fetched files enter storage → analysis path  

**Status:** Implemented in code; **hardware E2E unverified** in this audit. Unit coverage: `test_iec61850_fetch.py`.

### 5.3 Single-IED analysis → RCA → report → review

`POST /analyse` → job stages → engineering pipeline → protection/consistency/fault/RCA → HTML/PDF report → engineer review disposition.

**Status:** Implemented; RCA quality depends on digitals/settings/mapping.  
**Sticky ANALYZING / orphaned PENDING jobs:** heal/re-kick logic exists (`analysis_service.heal_stuck_analysis`) after prior defects.

### 5.4 Cascade / LBB combined analysis

1. `/analysis/cascade`: pick two events + INITIATOR/BACKUP roles  
2. `combined_analysis.run_combined_analysis` creates **new** `EVT-COMB-CASC-YYYY-NNNNN`, copies files with end labels  
3. Enqueues analysis; cascade enrichment (`cascade_lbb.py`) + dual COMTRADE ingest by end  
4. DR workspace: side-by-side / stacked / overlay + sync offset alignment (`dualEndWaveforms.ts`)

**Status:** Partially implemented → **recently verified** path for sample LV/HV LBB pair (`EVT-COMB-CASC-2026-00004`: dual COMTRADE ends, BF CONFIRMED).  
**Defects found & fixed in recent work (still regression-sensitive):**

- Engineering crash typo `ct_vt_params` vs `ct_vt_ratios`  
- Orphaned background analysis queue  
- Dual-end ingest grouping  

**Gaps vs Excel LBB matrix:** no formal 10-step LBB checklist as executable engine; compound classification string not structured; bus-fault exclusion rule is narrative/heuristic, not matrix-driven.

### 5.5 Local/Remote (line multi-end)

Same combined-event machinery with LOCAL/REMOTE roles. Electrical **87L operate/restraint comparison across terminals** is **not** proven as a dedicated multi-terminal calculator in the combined path — differential appears mainly as protection-element / RCA token logic when digitals/settings support it.

**Status:** Dual-end packaging **implemented**; true multi-terminal differential assessment **partial / unverified**.

### 5.6 Parent incident correlation

**Missing.** No automatic merge of independent IED events into a parent incident with local + incident RCA. Users manually build combined events.

---

## 6. Feature inventory (status legend)

| Status | Meaning |
|--------|---------|
| **IV** | Implemented and verified (code + tests or demonstrated run) |
| **IU** | Implemented, unverified (no field/E2E proof in this audit) |
| **P** | Partial |
| **UI** | UI/placeholder without full backend |
| **M** | Missing |
| **D** | Defective (known failing tests or reproducible bug) |

| Capability | Status | Evidence |
|------------|--------|----------|
| Plant hierarchy CRUD | IV | Plant API + PlantPage |
| IED metadata / peer link | IU | `remote_peer.py`, IED UI |
| Manual DR upload | IV | files API + IED workspace |
| IEC 61850 fetch / auto-fetch | IU | client + auto_fetch + tests |
| COMTRADE parse (multi-format) | IV | `comtrade/` + golden tests |
| Channel / digital maps | IV | DR APIs + pages |
| Waveforms + DR workspace | IV | WaveformViewer, DrWorkspace |
| Dual-end sync / overlay (SIGRA-like) | P | Frontend utils; sync from trigger timestamps |
| Protection assessment | IV | protection ops + page |
| Consistency checker | IV | consistency + tests |
| Fault classification | D/P | Engine present; **some pytest failures** |
| Fault location (21) | IU | FaultLocationPage + location module |
| RCA hypotheses | D/P | `HypothesisEngine` + YAML; **some pytest failures** |
| Cascade detect / combined cascade | P/IV | Services + combined UI; matrix not integrated |
| Line multi-end packaging | P | Combined UI; weak electrical 87L dual-end |
| Parent incident correlation | M | No model |
| L1/L2/L3 scenario matrix engine | M | Excel external only |
| Reports HTML/PDF | IV | report_service + templates |
| Engineer review | IV | ReviewPage + API |
| Auth local JWT | IV | auth API |
| OIDC | IU | Code paths; IdP config required |
| Dashboard | IV | dashboard API + page |
| Audit log | IV | AuditPage |
| Similarity (classical) | IU | Supporting scores |
| ML scoring | P | Often “NOT AVAILABLE” |
| Celery workers | IU | Code; portable uses BackgroundTasks |
| EXE / portable share | IV | Build scripts (frontend tsc must pass) |

---

## 7. RCA engine vs Excel matrix

| Matrix concept | App today |
|----------------|-----------|
| L1 relay bits | Digitals → protection operations / evidence tokens |
| L2 SOE | Side-file SOE + timeline merge |
| L3 DR | Waveforms, electrical, fault features |
| Explicit fallback paths | Ad-hoc Python heuristics, not declarative matrix rows |
| Confidence CONFIRMED/PROBABLE/POSSIBLE | RCA statuses exist (also INCONCLUSIVE etc.) — taxonomy not fully aligned |
| LBB 10-step checklist | Partial via cascade_lbb + BREAKER_FAILURE / INTERTRIP hypotheses |
| “Cascade ≠ bus fault” | Partially encoded in cascade notes / ranking; not hard rule engine |
| Asset-specific scenarios (motor jam, HIF, overflux…) | Some hypotheses; **far fewer than matrix rows** |

**Implication:** Improving RCA should **extend** `rules/rca/hypotheses.yaml` + `HypothesisEngine` (and optionally load a versioned matrix), **not** invent a second parallel engine.

---

## 8. Data integrity & reliability observations

| Topic | Finding |
|-------|---------|
| Immutable uploads | SHA-256 storage keys — good |
| Duplicate events | Combined path always creates new event; single-IED dedup of “same disturbance” is weak |
| Late-arriving peer DR | Can re-run / re-combine manually; no automatic incident update |
| Reprocessing | `force` analysis supersedes active jobs; versioning of RCA rule results on event is limited |
| Config change vs history | Settings verification flags exist; silent historical rewrite risk if settings change without audit |
| Background jobs | Orphan PENDING heal exists; still operationally fragile vs Celery |
| Dual DB | Auth isolation good; cross-DB referential integrity none |

---

## 9. Security & safety (verified claims)

- No OT trip/control endpoints (stated in `main.py` / docs)  
- Role hierarchy: VIEWER < ANALYST < PROTECTION_ENGINEER < APPROVER < ADMIN  
- JWT + bcrypt local auth  
- Upload size/extension limits via settings  
- Secrets in `.env` (must not commit); portable bootstrap admin defaults  

**Unverified:** production secret management, firewall, multi-tenant isolation (product appears single-plant DB).

---

## 10. Test & build baseline

```text
cd backend && python -m pytest tests/ -q
→ 401 passed, 11 failed, 1 skipped (2026-10-09)
```

Failing modules (sample): `test_decision.py`, `test_fault_classification.py`, `test_inrush_charging_framing.py`, `test_rca.py`.

Frontend: `npm run build` (tsc + vite) — required for EXE packaging.

---

## 11. Documentation already in repo

| Doc | Note |
|-----|------|
| `docs/IMPLEMENTATION_STATUS.md` | Partially **stale** (e.g. `/events/new` wizard) |
| `docs/ARCHITECTURE.md`, `API.md`, `RCA_ENGINE.md`, … | Useful but may lag code |
| `docs/USER_GUIDE.md` | Operational guide |
| This file | **Authoritative current-state for the master-prompt program** |

---

## 12. Open questions (cannot answer from code alone)

1. Which production environments use Postgres + Celery vs SQLite + BackgroundTasks?  
2. Are any real substations’ IEC 61850 auto-fetch configs authoritative for timing/LBB?  
3. Should Local/Remote be renamed to Line Differential in UI, or kept as dual-end generic?  
4. Is the Excel matrix the **target executable rulebook**, or an advisory engineering checklist?  
5. Desired identity for “incident”: new table vs tagging existing combined events?  

---

## 13. Recommended next phases (no implementation in this document)

Per master prompt, **do not rewrite**. Next deliverables:

1. **`GAP_ANALYSIS_AND_ROADMAP.md`** — prioritize: (a) fix failing RCA/decision tests, (b) wire L1/L2/L3/LBB matrix into existing RCA without a second engine, (c) strengthen cascade compound classification, (d) parent-incident model only after correlation rules are clear, (e) real 87L dual-terminal checks when measurements allow.  
2. Preserve Cascade/LBB and Local/Remote tabs; extend in place.  
3. Align `IMPLEMENTATION_STATUS.md` with this audit.

---

## 14. Evidence index (key paths)

| Area | Paths |
|------|-------|
| App entry | `backend/app/main.py`, `frontend/src/App.tsx` |
| Models | `backend/app/models/__init__.py` |
| Analyse / combined | `backend/app/api/analysis.py`, `services/combined_analysis.py` |
| Engineering | `backend/app/services/engineering_persist.py`, `analysis_pipeline.py` |
| Cascade | `backend/app/services/cascade_lbb.py` |
| RCA | `backend/rca/__init__.py`, `rules/rca/hypotheses.yaml` |
| COMTRADE | `backend/comtrade/` |
| IEC61850 | `backend/app/services/iec61850/` |
| Dual-end UI | `frontend/src/pages/DrWorkspacePage.tsx`, `utils/dualEndWaveforms.ts` |
| Combined UI | `frontend/src/pages/CombinedAnalysisPage.tsx` |

---

*End of Phase One audit. No product code was changed for this document.*
