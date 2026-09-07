# Database

## Technology

- **PostgreSQL 16** (Compose service `postgres`)
- **SQLAlchemy 2.0** async ORM (`asyncpg`)
- **Alembic** migrations (`backend/alembic.ini`, run on container start)

ORM models: `backend/app/models/__init__.py`  
Base / session: `backend/app/database.py`

Default DB (dev): `protection_rca` · user `protection` · password `protection_dev_only`

## Entity groups

### Identity & access

| Table | Purpose |
|-------|---------|
| `users` | Accounts, hashed passwords, role enum string |
| `roles` | Optional role catalogue / permissions JSON |

Roles used in auth: `VIEWER`, `ANALYST`, `PROTECTION_ENGINEER`, `APPROVER`, `ADMIN`.

### Asset hierarchy

`substations` → `bays` → `relays` / `breakers` / `assets`

### Settings

| Table | Purpose |
|-------|---------|
| `setting_groups` | Named banks / group numbers |
| `setting_versions` | Immutable packages, approval status |
| `settings` | Parameter rows (`parameter`, `value`, `enabled`, `element`, …) |

### Events & files

| Table | Purpose |
|-------|---------|
| `events` | Disturbance case; status, decision_state, tags |
| `event_files` | Immutable uploads (`sha256`, `storage_key`) |
| `comtrade_files` | Parsed COMTRADE metadata + validation_status |
| `comtrade_channels` | Analog/digital channel defs |

### Measurements & operations

| Table | Purpose |
|-------|---------|
| `measurements` | Derived quantities (RMS, phasor, Z, …) |
| `event_timeline` | Ordered reconstruction (`t_us`, `event_type`) |
| `protection_operations` | Pickup/trip/target assertions |

### Analysis results

| Table | Purpose |
|-------|---------|
| `consistency_findings` | Consistency checker outputs |
| `fault_classifications` | Fault type / distance / confidence |
| `anomalies` | Anomaly records (optional ML) |
| `rca_hypotheses` | Ranked hypotheses |
| `evidence` | Supporting / contradicting items |
| `similar_events` | Similarity links |

### Documents, reports, reviews

`documents`, `reports`, `engineer_reviews`

### Governance

| Table | Purpose |
|-------|---------|
| `audit_log` | User/system actions (admin may clear; CLEAR entry retained) |
| `rule_versions` | Versioned rule packages |
| `model_versions` | Optional statistical model artefacts |
| `analysis_jobs` | Celery job progress, stages, component versions |

## Identifiers

Most tables use UUID string primary keys (`UUIDPrimaryKeyMixin`) plus `created_at` / `updated_at` where applicable. Business `event_id` / `setting_id` / `finding_id` columns exist alongside surrogate `id`.

## Object storage vs DB

Binary file bytes live in **MinIO/S3** (or local `STORAGE_BACKEND=local`). Postgres stores keys, hashes, and parsed metadata — not raw COMTRADE payloads in-row.

## Migrations

```bash
cd backend
alembic upgrade head
```

Compose backend command runs migrations before uvicorn.
