# Deployment

## Local — Docker Compose

File: `docker-compose.yml`

| Service | Image / build | Ports |
|---------|---------------|-------|
| `postgres` | postgres:16-alpine | 5432 |
| `redis` | redis:7-alpine | 6379 |
| `minio` | minio/minio | 9000 API, 9001 console |
| `minio-init` | minio/mc | creates bucket `protection-rca` |
| `backend` | `docker/Dockerfile.backend` | 8000 |
| `worker` | same image, Celery | — |
| `frontend` | `docker/Dockerfile.frontend` | 5173 |

Start:

```bash
cd protection-rca
docker compose up --build
```

Backend startup: `alembic upgrade head` → `uvicorn app.main:app --reload`  
Worker: `celery -A workers.celery_app worker --loglevel=INFO`

Environment is loaded from `.env.example` (override with `.env` as needed). Critical variables:

- `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`
- `S3_ENDPOINT`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`, `S3_BUCKET`
- `SECRET_KEY`, `CORS_ORIGINS`
- `RUN_ANALYSIS_SYNC` (true for simple local/test; false to use Celery)

Volumes mount `backend/`, `rules/`, `templates/`, `models/`, `test_data/` for live development.

---

## Local — hybrid

Run only infra in Compose:

```bash
docker compose up postgres redis minio minio-init
```

Then run API / worker / frontend on the host (see README). Point `DATABASE_URL` and `S3_ENDPOINT` at localhost ports.

---

## AWS reference architecture

Target production pattern (map Compose services to managed AWS):

```
Internet → CloudFront → ALB → ECS (API + worker tasks)
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
            RDS            ElastiCache      S3
         (PostgreSQL)       (Redis)     (object store)
              │
         Secrets Manager ← app env / task role
```

| Local | AWS |
|-------|-----|
| frontend (Vite) | Static build on **S3** + **CloudFront** (or container behind ALB) |
| FastAPI | **ECS Fargate/EC2** service behind **ALB** |
| Celery worker | Separate **ECS** service (same image, different command); scale independently |
| Redis | **ElastiCache** Redis (broker + results) *or* **Amazon SQS** as Celery broker with result backend policy of your choice |
| PostgreSQL | **Amazon RDS** PostgreSQL |
| MinIO | **Amazon S3** (`S3_ENDPOINT` empty/default AWS, SSL on, IAM task role preferred over static keys) |
| `.env` secrets | **AWS Secrets Manager** / SSM Parameter Store injected into task definitions |

### Suggested practices

1. **CloudFront** terminates TLS; forward to ALB origin for API (`/api/*`) and static SPA.
2. **ALB** health check: `GET /health` (expects `ot_control_plane: disabled`).
3. **ECS** task role: `s3:GetObject/PutObject` on the bucket; `secretsmanager:GetSecretValue` for DB URL / JWT secret.
4. **RDS**: private subnets; TLS; no public exposure; migrate with Alembic as a one-off task or init container.
5. **S3**: versioning optional; objects remain content-addressed; block public access.
6. **SQS** (optional): if replacing Redis broker, configure Celery SQS transport and keep analysis idempotent via `analysis_jobs`.
7. **Secrets Manager**: `SECRET_KEY`, DB credentials, OIDC client secret (if `AUTH_MODE` moves beyond local JWT). Never bake secrets into images.
8. **CORS**: set `CORS_ORIGINS` to the CloudFront SPA origin only.

### Auth in AWS

Development uses local JWT (`AUTH_MODE=local`). For enterprise, configure OIDC settings (`OIDC_ISSUER`, `OIDC_CLIENT_ID`, …) and terminate auth at the API or API Gateway as required by your IdP — still **no OT control plane**.

### Observability

Enable structured logs (`LOG_LEVEL`, structlog) and metrics (`ENABLE_METRICS`). Ship container logs to CloudWatch; retain `X-Request-ID` for correlation.

---

## Hardening checklist before production

- [ ] Rotate all default passwords (`admin/admin123`, Postgres, MinIO/IAM)
- [ ] Strong unique `SECRET_KEY`
- [ ] `DEBUG=false`, `APP_ENV=production`
- [ ] TLS everywhere (CloudFront/ALB/RDS/S3)
- [ ] Restrict security groups; no public RDS/Redis
- [ ] Confirm no control endpoints registered (router audit)
- [ ] Backup RDS + S3 lifecycle policies
