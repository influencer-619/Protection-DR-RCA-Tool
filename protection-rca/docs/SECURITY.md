# Security

## OT read-only boundary

This platform is **analysis and reporting only**.

- FastAPI router registers no breaker trip, relay control, SCADA write, or field-device command APIs (`app/api/router.py`, `app/main.py`).
- Health payload includes `"ot_control_plane": "disabled"`.
- Engineer review / approve changes **database disposition state** only — never field equipment.

Treat any future control feature as out of scope unless separately designed, certified, and isolated.

## Authentication

- Default: local JWT (`AUTH_MODE=local`) via `POST /api/auth/login`.
- Passwords hashed with bcrypt (`passlib`).
- Tokens: HS256 JWT, claims `sub`, `role`, `exp` (`ACCESS_TOKEN_EXPIRE_MINUTES`, default 480).
- `SECRET_KEY` must be long and random outside local demos.
- OIDC fields are reserved for enterprise IdP integration (`OIDC_*`).

## RBAC

Roles (`app.core.security.Role`) with hierarchy:

| Role | Level | Typical capabilities |
|------|------:|----------------------|
| VIEWER | 1 | Read authenticated endpoints |
| ANALYST | 2 | Events, uploads, COMTRADE utils, analyse, reports |
| PROTECTION_ENGINEER | 3 | Settings create, submit review |
| APPROVER | 4 | Approve/close, read audit |
| ADMIN | 5 | Users, assets CRUD, activate rules/models |

`require_role(min)` allows the required role or any higher level.

Sensitive examples:

- User admin: `ADMIN`
- Asset create: `ADMIN`
- Settings write: `PROTECTION_ENGINEER`
- Analyse / upload: `ANALYST`
- Audit list: `APPROVER`

## Upload validation

`file_service` enforces:

1. Extension allow-list (`ALLOWED_UPLOAD_EXTENSIONS`)
2. Max size (`MAX_UPLOAD_SIZE_MB`)
3. Streaming SHA-256
4. Immutable `event_files` row; content-addressed object key
5. Duplicate `(event_id, sha256)` handling without overwriting storage semantics

Do not widen the allow-list to executable types without a security review.

## Middleware & transport

- CORS restricted to configured origins
- Security headers middleware
- Per-request `X-Request-ID`
- Rate limiting (`RATE_LIMIT_PER_MINUTE`, default 120)

## Secrets

| Secret | Guidance |
|--------|----------|
| `SECRET_KEY` | JWT signing; Secrets Manager in AWS |
| DB password | Never commit production values; Compose default is **dev-only** |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | Prefer IAM roles on ECS; MinIO keys for local only |
| OIDC client secret | Secrets Manager; never front-end |

`.env.example` is a template — not a production secret store.

## Audit

Mutating and security-relevant actions write `audit_log` (login, upload, review, approve, user create, …). Approvers can query via `/api/audit`. Admins may clear the log via `DELETE /api/audit` (a single `CLEAR` entry is retained for the actor).

## Generative AI

No LLM API keys are part of the security model because **generative AI is not used**. Model registry is for optional non-generative statistical artefacts only.

## Default seed accounts

`admin` / `admin123` (and demo analyst/engineer) exist for empty-DB bootstrap. **Disable or rotate immediately** on shared systems.
