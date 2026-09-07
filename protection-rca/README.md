# Protection RCA

Protection Disturbance Record (DR) / COMTRADE analysis / Root Cause Analysis
**web application** for protection engineers.

**No generative AI. No OT control.** Deterministic engineering analysis only.

## Status

See [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md) for an honest
map of what works vs what is still partial.

Generate COMTRADE golden fixtures (once):

```bash
python scripts/generate_comtrade_fixtures.py
```

## Stack

- Frontend: React + TypeScript + Vite (dark engineering console)
- Backend: FastAPI + SQLAlchemy
- DB: PostgreSQL (Compose) / SQLite (local scripts)
- Workers: Celery + Redis (Compose); sync pipeline in local development
- Storage: MinIO/S3 pattern (Compose)

## Quick start (local)

1. `scripts/start-all.bat` or `ProtectionRCA.exe`
2. UI: http://127.0.0.1:5173 (dev) or http://127.0.0.1:8001 (portable with `frontend/dist`)
3. Create admin via `BOOTSTRAP_ADMIN_*` env if needed

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

## Workflow

Create Event → Upload package → Detect → Validate COMTRADE → Analyse →
Consistency → RCA → Evidence → Report → Engineer review

Guided UI: **/events/new**

## Tests

```bash
cd backend
python -m pytest tests/ -q
```

## Documentation

`docs/` — architecture, API, COMTRADE, consistency, RCA, security, user guide.
