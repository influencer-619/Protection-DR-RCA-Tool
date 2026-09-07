# Implementation status vs complete webapp specification

This document describes **what is implemented today** in Protection RCA.
It does not claim unfinished features as complete.

## Working (browser + API)

- Dark engineering-console UI (sidebar, KPIs, event workspace tabs)
- Auth: local JWT + **optional OIDC** (`AUTH_MODE=oidc`, `/api/auth/mode`, `/api/auth/oidc/callback`)
- Events CRUD, file upload with SHA-256 / immutable storage keys
- Guided **Create Event** wizard (`/events/new`)
- COMTRADE detect / validate / parse (IEEE/IEC, ASCII/Binary/Binary32/Float32, CFF)
- Analysis pipeline persists COMTRADE metadata + **waveform sample cache**
- Waveform API returns sample arrays (`GET /api/events/{id}/waveforms`)
- Protection physics: **51 IEC/IEEE inverse curves**, **21 mho/quad zone entry**
- Consistency checker (incl. 51 enabled=FALSE + pickup/trip → INCONSISTENT)
- RCA / evidence / engineer review
- Reports: **JSON + Jinja HTML + ReportLab PDF** (`/api/reports/{id}/download`)
- Classical historical similarity (cosine features; supporting evidence only)
- Dashboard: clickable KPIs, 7/30/90 trend, DQ, attention, empty states
- Alembic **`0001_initial_schema`** creates full ORM schema
- Docker Compose (postgres, redis, minio, backend, worker, frontend)
- Golden COMTRADE matrix fixtures + regression tests
- Unit/integration/acceptance tests (70+)

## Partial / deferred (honest)

| Area | Status |
|---|---|
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
