# REST API

Base URL (local): `http://localhost:8000`

Interactive docs: `/docs` · ReDoc: `/redoc`

Unless noted, endpoints require `Authorization: Bearer <access_token>`.

Roles (hierarchy, higher includes lower privileges for `require_role`):  
`VIEWER` < `ANALYST` < `PROTECTION_ENGINEER` < `APPROVER` < `ADMIN`

---

## Health

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | none | Liveness; `ot_control_plane: disabled` |
| GET | `/api/health` | none | Same |

---

## Auth — `/api/auth`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| POST | `/api/auth/login` | none | Body: `{ "username", "password" }` → JWT + user |

---

## Users — `/api/users`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| GET | `/api/users/me` | authenticated | Current user |
| GET | `/api/users` | ADMIN | List users |
| POST | `/api/users` | ADMIN | Create user |
| PATCH | `/api/users/{user_id}` | ADMIN | Update user |

---

## Events — `/api/events`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| POST | `/api/events` | ANALYST | Create event |
| GET | `/api/events` | authenticated | List (`page`, `page_size`, `status`, `substation_id`) |
| GET | `/api/events/{event_id}` | authenticated | Get event (UUID or business `event_id`) |
| PATCH | `/api/events/{event_id}` | ANALYST | Update event metadata |
| POST | `/api/events/{event_id}/approve-settings` | ANALYST | Approve uploaded settings file (`also_verify_active_group`) |
| POST | `/api/events/{event_id}/verify-active-settings` | ANALYST | Confirm active setting group only |
| DELETE | `/api/events/{event_id}` | ANALYST | Delete event (audited) |

---

## Files — `/api/events`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| POST | `/api/events/{event_id}/files` | ANALYST | Multipart upload (`file`, optional `source_type`) |

Allowed extensions (config): `.cfg,.dat,.cff,.hdr,.inf,.csv,.txt,.xml,.json,.pdf,.zip`  
ZIP uploads are auto-extracted; each allowed member is stored and processed (COMTRADE/settings/SOE). The original ZIP is kept as a PACKAGE attachment.  
Max size: `MAX_UPLOAD_SIZE_MB` (default 200).

---

## COMTRADE utilities — `/api/comtrade`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| POST | `/api/comtrade/detect` | ANALYST | Multipart file list → detection status / revision / format |
| POST | `/api/comtrade/validate` | ANALYST | Parse + validate → validation status / issues |
| POST | `/api/comtrade/parse` | ANALYST | Full ingest → record summary + detection/validation |

These endpoints are analysis-only (temporary files; no OT control).

---

## Settings — `/api/settings`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| POST | `/api/settings` | PROTECTION_ENGINEER | Create setting row |
| GET | `/api/settings` | authenticated | List (`relay_id`, pagination) |
| GET | `/api/settings/{setting_id}` | authenticated | Get one |

---

## Analysis — `/api`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| POST | `/api/analyse` | ANALYST | Body: `{ "event_id", "parameters?", "force?" }` → enqueue/start job |
| GET | `/api/analysis-status/{job_id}` | authenticated | Job progress / stage |
| GET | `/api/events/{event_id}/timeline` | authenticated | Timeline entries |
| GET | `/api/events/{event_id}/waveforms` | authenticated | Waveform channel summary / samples metadata |
| GET | `/api/events/{event_id}/electrical` | authenticated | Electrical summary |
| GET | `/api/events/{event_id}/protection` | authenticated | Protection assessments |
| GET | `/api/events/{event_id}/consistency` | authenticated | Consistency findings |
| GET | `/api/events/{event_id}/fault` | authenticated | Fault classification(s) |
| GET | `/api/events/{event_id}/rca` | authenticated | RCA hypotheses + primary |
| GET | `/api/events/{event_id}/evidence` | authenticated | Evidence list |

---

## Reports — `/api/reports`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| POST | `/api/reports` | ANALYST | Generate report for event |
| GET | `/api/reports/by-event/{event_id}` | authenticated | List reports |
| GET | `/api/reports/{report_id}` | authenticated | Get report |

---

## Review — `/api/review`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| POST | `/api/review` | PROTECTION_ENGINEER | Submit disposition (`ACCEPT`, `MODIFY`, `REJECT`, `INCONCLUSIVE`, `REQUEST_FIELD_INVESTIGATION`) |
| POST | `/api/review/approve` | APPROVER | Final accept / close |
| GET | `/api/review/event/{event_id}` | authenticated | List reviews |

Review changes event status / decision state only — **no field control**.

---

## Assets — `/api`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| POST | `/api/substations` | ADMIN | Create |
| GET | `/api/substations` | authenticated | List |
| GET | `/api/substations/{substation_id}` | authenticated | Get |
| POST | `/api/bays` | ADMIN | Create |
| GET | `/api/bays` | authenticated | List (`substation_id`) |
| POST | `/api/relays` | ADMIN | Create |
| GET | `/api/relays` | authenticated | List (`substation_id`, `bay_id`) |
| GET | `/api/relays/{relay_id}` | authenticated | Get |
| POST | `/api/breakers` | ADMIN | Create |
| GET | `/api/breakers` | authenticated | List |
| POST | `/api/assets` | ADMIN | Create protected asset |
| GET | `/api/assets` | authenticated | List (`substation_id`, `asset_type`) |

---

## Rules registry — `/api/rules`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| GET | `/api/rules` | authenticated | List rule versions (`rule_family`, `active_only`) |
| POST | `/api/rules` | ADMIN | Register rule package |
| POST | `/api/rules/{rule_id}/activate` | ADMIN | Activate (deactivates peers in family) |

Families include `PROTECTION`, `CONSISTENCY`, `RCA`, `SIGNAL` (as stored).

---

## Model registry — `/api/models`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| GET | `/api/models` | authenticated | List statistical/ML artefacts |
| POST | `/api/models` | ADMIN | Register model version |
| POST | `/api/models/{model_id}/activate` | ADMIN | Activate |

**No generative AI models.** Registry is for optional classifiers / anomaly / similarity artefacts; engines default to NOT AVAILABLE without an active approved model.

---

## Audit — `/api/audit`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| GET | `/api/audit` | APPROVER | List audit log (`page`, `action`, `object_type`) |
| DELETE | `/api/audit` | ADMIN | Clear all audit entries; writes one `CLEAR` record |

---

## Dashboard — `/api/dashboard`

| Method | Path | Min role | Description |
|--------|------|----------|-------------|
| GET | `/api/dashboard/stats` | authenticated | Counts + recent events |

---

## Intentionally absent

There are **no** endpoints for:

- Breaker trip / close / open commands  
- Relay setting download-to-device or live write  
- SCADA / IEC 61850 control  
- Generative text completion  

See router comment in `backend/app/api/router.py` and health payload `ot_control_plane: disabled`.
