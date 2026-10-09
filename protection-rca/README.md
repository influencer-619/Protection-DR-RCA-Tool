# Protection RCA

Protection Disturbance Record (DR) / COMTRADE analysis / Root Cause Analysis
**web application** for protection engineers.

**No generative AI. No OT control.** Deterministic engineering analysis only.

## Status

See [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) for an honest
map of what works vs what is still partial. Gap roadmap:
[`docs/GAP_ANALYSIS_AND_ROADMAP.md`](docs/GAP_ANALYSIS_AND_ROADMAP.md).

Generate COMTRADE golden fixtures (once):

```bash
python scripts/generate_comtrade_fixtures.py
```

## Stack

- Frontend: React + TypeScript + Vite (dark engineering console)
- Backend: FastAPI + SQLAlchemy (async)
- DB: PostgreSQL + `asyncpg` (Compose) / SQLite + `aiosqlite` (local / portable EXE)
- Workers: Celery + Redis (Compose); deferred `asyncio` jobs locally (sync path when `RUN_ANALYSIS_SYNC=true`)
- Storage: MinIO/S3 pattern (Compose); local filesystem for portable

## Quick start (local)

1. `cd backend && pip install -r requirements.txt` (includes `aiosqlite` for SQLite URLs)
2. `scripts/start-all.bat` or `ProtectionRCA.exe`
3. UI: http://127.0.0.1:5173 (dev) or http://127.0.0.1:8001 (portable with `frontend/dist`)
4. Create admin via `BOOTSTRAP_ADMIN_*` env if needed

## Share with another PC / LAN access

Build a portable folder (no Node install on the other PC):

```bat
scripts\build-portable-share.bat
```

That creates `portable-share\` with `ProtectionRCA.exe`, `backend\.venv`, built UI, and `HOW_TO_RUN.txt`.

- **Recipient laptop:** unzip folder → double-click `ProtectionRCA.exe` → http://127.0.0.1:8001/
- **Network access:** while it runs on your laptop, others on the same LAN open the **LAN URL** shown in the control window (e.g. `http://192.168.x.x:8001/`). Allow Windows Firewall for port **8001** when prompted.

Do not send only the `.exe` — the whole `portable-share` folder is required.

## Docker

```bash
docker compose up --build
```

## Plant-first workflow

1. **Plant** (`/plant`) — stations / bays / IEDs  
2. Open an IED → upload DR packages (COMTRADE + side files)  
3. **Analyse** on the event (progress via analysis-status; sticky ANALYZING is auto-healed)  
4. **Combined analysis** for dual-end cases:
   - Cascade / LBB — `/analysis/cascade`
   - Local / Remote line — `/analysis/local-remote`
5. Review Summary → Protection → RCA → Waveforms → Report → Engineer review  

Legacy `/events/new` and `/upload` redirect to `/plant`.

## Tests

```bash
cd backend
python -m pytest tests/ -q
```

## Documentation

`docs/` — architecture, API, COMTRADE, consistency, RCA, security, audit, gap roadmap.
