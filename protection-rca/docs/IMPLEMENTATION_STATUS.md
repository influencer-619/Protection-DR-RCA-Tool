# Implementation status vs complete webapp specification

This document describes **what is implemented today** in Protection RCA.
It does not claim unfinished features as complete.

## Working (browser + API)

- Dark engineering-console UI (sidebar, KPIs, event workspace tabs)
- Auth: local JWT + **optional OIDC** (`AUTH_MODE=oidc`, `/api/auth/mode`, `/api/auth/oidc/callback`)
- **Plant-first** navigation (`/plant` → IED workspace); legacy `/events/new` / `/upload` redirect
- Events CRUD, file upload with SHA-256 / immutable storage keys
- COMTRADE detect / validate / parse (IEEE/IEC, ASCII/Binary/Binary32/Float32, CFF)
- Analysis pipeline persists COMTRADE metadata + **waveform sample cache**
- Deferred analyse (`asyncio` + BackgroundTasks backup); orphan PENDING heal / soft re-kick; sticky ANALYZING→REVIEW when results exist
- Waveform API returns sample arrays (`GET /api/events/{id}/waveforms`)
- **Combined RCA product removed** (no Cascade/Local–Remote create UI or `POST /combined-analysis`); Excel matrix LBB evidence scoring remains on single events
- Protection physics: **51 IEC/IEEE inverse curves**, **21 mho/quad zone entry**, ANSI C37.2 labels
- Consistency checker (incl. 51 enabled=FALSE + pickup/trip → INCONSISTENT)
- RCA / evidence / engineer review (HypothesisEngine + `hypotheses.yaml`)
- Reports: **JSON + Jinja HTML + ReportLab PDF** (`/api/reports/{id}/download`)
- Classical historical similarity (cosine features; supporting evidence only)
- Dashboard: clickable KPIs, 7/30/90 trend, DQ, attention, empty states
- Alembic **`0001_initial_schema`** creates full ORM schema
- Docker Compose (postgres, redis, minio, backend, worker, frontend); local/portable **SQLite + aiosqlite**
- Golden COMTRADE matrix fixtures + regression tests
- Unit/integration/acceptance tests (390+)

## Partial / deferred (honest)

| Area | Status |
|---|---|
| Excel L1/L2/L3/LBB matrix as executable pack | **Full pack** — `matrix_v1.yaml` v1.1.0 = all **54** Excel scenarios + LBB 10-step + fallback methodology + bus guardrail (`docs/reference/…xlsx`) |
| True 87L dual-terminal electrical compare | **Removed with Combined RCA** — dual-end create path retired; plant peer links remain for reference |
| Parent Incident entity | **Stage E shipped** — Incident + members; manual link/unlink/late attach; no time-only merge |
| pgvector ANN index | Classical cosine shipped; pgvector image/extension optional future |
| WeasyPrint CSS PDF | ReportLab PDF packaging shipped; WeasyPrint remains optional |
| Full electrical RMS/phasor persist on every analyse | Wired path exists; enrich when channels mapped |
| OIDC UI callback code exchange | Authorize URL + callback API ready; IdP must be configured |
| Deep 87/67 directional polarizing physics | Element modules present; curve/zone depth focused on 51/21 |

## Engineering safety (enforced)

- No invented measurements, settings, timestamps, fault distance
- No silent COMTRADE repair
- Settings hierarchy shows NOT VERIFIED when active group unverified
- Consistency INCONSISTENT ≠ relay malfunction CONFIRMED
- No OT write/control endpoints
- No generative AI

## How to run

See root `README.md`. Regenerate COMTRADE fixtures:

```bash
python scripts/generate_comtrade_fixtures.py
```
