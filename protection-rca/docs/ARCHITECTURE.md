# Architecture

## Purpose

Protection RCA is a **read-only analysis** platform for COMTRADE disturbance records and protection settings. It reconstructs events, assesses protection element behaviour, checks consistency against settings, and ranks evidence-gated root-cause hypotheses.

It is **not** a control system, SCADA gateway, or generative-AI assistant.

## Logical architecture

```
┌─────────────┐     ┌──────────────────────────────────────────┐
│ React UI    │────▶│ FastAPI (app.main)                        │
│ Vite :5173  │     │  /api/*  JWT RBAC  rate limit  audit      │
└─────────────┘     └───────┬───────────────┬──────────────────┘
                            │               │
                     ┌──────▼──────┐ ┌──────▼──────┐
                     │ PostgreSQL  │ │ Redis       │
                     │ ORM + Alembic│ │ broker/cache│
                     └─────────────┘ └──────┬──────┘
                                            │
                     ┌─────────────┐ ┌──────▼──────┐
                     │ MinIO / S3  │ │ Celery      │
                     │ immutable   │ │ worker      │
                     │ file bytes  │ │ pipeline    │
                     └─────────────┘ └─────────────┘
```

## Runtime components

| Component | Role |
|-----------|------|
| **Frontend** | React 18 + Vite; event workspace (upload, waveforms, protection, consistency, RCA, review) |
| **API** | FastAPI async app; JWT auth; hierarchical RBAC; OpenAPI |
| **PostgreSQL 16** | Authoritative metadata, analysis results, audit |
| **Redis 7** | Celery broker (`/0`) and result backend (`/1`) |
| **MinIO** | S3-compatible object storage for uploaded files (content-addressed keys) |
| **Celery worker** | Runs `AnalysisJob` pipeline stages when `RUN_ANALYSIS_SYNC=false` |
| **Rules / templates** | Versioned YAML under `rules/`; Jinja report + sentence templates under `templates/` |

## Analysis pipeline

Job stages (`JobStage` enum) in order:

1. `UPLOAD` / file association  
2. `FILE_DETECTION` — COMTRADE detect  
3. `COMTRADE_VALIDATION` — structural validation (no silent repair)  
4. `PARSING` — canonical disturbance record  
5. `SIGNAL_PROCESSING` — RMS, phasors, frequency, impedance where calculable  
6. `EVENT_RECONSTRUCTION` — timeline (pickup, trip, breaker, interruption, …)  
7. `PROTECTION_ANALYSIS` — modular ANSI elements + settings resolution  
8. `CONSISTENCY_CHECKER` — enabled/pickup/trip, sequence, family checks  
9. `FAULT_CLASSIFICATION` — AG…ABCG / UNKNOWN; distance may be `NOT_CALCULABLE`  
10. `RCA` — hypothesis scoring; forced INCONCLUSIVE on critical setting inconsistency  
11. `EVIDENCE` — evidence graph items  
12. `REPORT` — deterministic template render  
13. `COMPLETE` or `FAILED`

Orchestration: `app.services.analysis_service` / `analysis_pipeline`, executed by Celery task `workers.tasks` or in-process when `RUN_ANALYSIS_SYNC=true`.

## Engineering modules (backend packages)

| Package | Responsibility |
|---------|----------------|
| `comtrade/` | Detect, parse (IEEE/IEC revisions), scale, timestamps, validate, quality |
| `signal_processing/` | Electrical quantities from waveforms |
| `event_reconstruction/` | Timeline events from analogs/digitals |
| `settings/hierarchy/` | Explicit setting source resolution (`VERIFIED` / `NOT_VERIFIED`) |
| `protection/` | YAML-driven element assessments |
| `consistency/` | Consistency findings; critical disabled-operate rule |
| `fault_analysis/` | Fault type + distance with calculability gates |
| `rca/` | Hypothesis engine with evidence requirements for CONFIRMED |
| `decision/` | Aggregate decision state for the event |
| `anomaly/` / `similarity/` | Optional; default `ML RESULT: NOT AVAILABLE` / `SIMILARITY RESULT: NOT AVAILABLE` |
| `reporting/` | Template reports (no LLM) |
| `evidence/` | Evidence packaging |
| `audit/` | Immutable action log |

## Data flow (files)

1. Upload via `POST /api/events/{id}/files`  
2. Extension allow-list + size limit; SHA-256; store under `{prefix}/{sha256[:2]}/{sha256}`  
3. Rows in `event_files` are immutable (no overwrite of same content key)  
4. Pipeline reads objects from MinIO/local storage and writes structured results to Postgres  

## Frontend / API contract

- Bearer JWT from `POST /api/auth/login`
- Base path `/api/...`
- Health: `/health` and `/api/health` (includes `"ot_control_plane": "disabled"`)

## Explicit non-goals

- Breaker trip / relay setting write / SCADA control
- Generative narrative RCA
- Claiming unsupported COMTRADE variants as fully validated
- Auto-concluding relay malfunction from settings inconsistency alone

See also [COMTRADE_SUPPORT.md](COMTRADE_SUPPORT.md), [CONSISTENCY_CHECKER.md](CONSISTENCY_CHECKER.md), [RCA_ENGINE.md](RCA_ENGINE.md).
