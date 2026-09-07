# Protection RCA — User Guide

**Audience:** Protection engineers, analysts, approvers, and administrators  
**Product:** Protection Disturbance Record (DR) / COMTRADE analysis and Root Cause Analysis (RCA) platform  
**Document version:** 0.3.0  
**Application:** Protection RCA web application (React + FastAPI)

This guide explains how to launch the application, create and analyse disturbance events, interpret results, generate reports, and complete engineer review. It reflects the **current implemented behaviour** of the platform.

---

## Document revision — what is covered in this edition

This edition documents the latest platform upgrades, including:

| Area | What changed |
|------|----------------|
| **Portable package** | `scripts\build-portable-share.bat` builds a shareable folder (exe + backend venv + built UI) — no Python/Node install on the other PC |
| **LAN access** | Launcher binds API/UI for network use; control window shows LAN URLs (e.g. `http://192.168.x.x:8001/`) |
| **Portable run mode** | When `frontend\dist` exists, exe serves UI+API on **port 8001** (single process); otherwise Vite UI on **5173** |
| **Dashboard** | Clickable KPI tiles, 7/30/90-day trend, data-quality donut, Attention Required, richer Recent Events, empty-state workflow |
| **Navigation** | Grouped sidebar: Operations · Plant · Engineering · Administration · Help |
| **Create Event wizard** | Multi-step page at `/events/new`: Info → Upload → Detect → Validate → Analyse |
| **Event workspace** | Pipeline status bar (COMTRADE / DATA / SETTINGS / PROTECTION / CONSISTENCY / RCA / REPORT) |
| **Overview** | What happened · Why · Which setting · What is uncertain · What should I verify |
| **Waveforms** | Real sample streaming from parsed COMTRADE (cached samples, not metadata-only) |
| **Protection physics** | Element **51** IEC/IEEE inverse-time curves; Element **21** mho/quad zone reach |
| **RCA hypotheses** | Zone-aware ranking (e.g. 87T → transformer internal; lightning/vegetation only for line/feeder with evidence) |
| **Reports** | Deterministic HTML + **PDF download** (ReportLab); JSON machine-readable companion |
| **Upload attachments** | **`.pdf`** and **`.zip`** allowed; ZIP packages **auto-extract** and each allowed member is stored/processed |
| **Delete event** | Events list Actions → Delete; also Delete on event workspace header (ANALYST+) |
| **Similarity** | Classical cosine historical similarity (supporting evidence only — never proof) |
| **COMTRADE matrix** | Fixtures for IEEE 1991, BINARY, BINARY32, FLOAT32, CFF + golden expectations |
| **Authentication** | Local JWT login; optional **OIDC / SSO** when `AUTH_MODE=oidc` |
| **Database** | Alembic initial schema migration; PostgreSQL (Compose) / SQLite (local scripts) |
| **Safety** | Still **no generative AI**, **no OT control**, no invented measurements/distance |

---

## Table of contents

1. [What this tool is (and is not)](#1-what-this-tool-is-and-is-not)
2. [Starting and stopping the application](#2-starting-and-stopping-the-application)
3. [Signing in (local and SSO)](#3-signing-in-local-and-sso)
4. [Roles and permissions](#4-roles-and-permissions)
5. [Main navigation](#5-main-navigation)
6. [Dashboard (operations console)](#6-dashboard-operations-console)
7. [Recommended workflow (end-to-end)](#7-recommended-workflow-end-to-end)
8. [Create Event wizard (guided)](#8-create-event-wizard-guided)
9. [Uploading files](#9-uploading-files)
10. [COMTRADE detection and validation](#10-comtrade-detection-and-validation)
11. [Running analysis](#11-running-analysis)
12. [Event analysis workspace (detailed)](#12-event-analysis-workspace-detailed)
13. [Protection physics (51 and 21)](#13-protection-physics-51-and-21)
14. [Understanding status badges and quality labels](#14-understanding-status-badges-and-quality-labels)
15. [Settings and setting hierarchy](#15-settings-and-setting-hierarchy)
16. [Assets (substations, bays, relays, breakers)](#16-assets-substations-bays-relays-breakers)
17. [Rules, models, and historical similarity](#17-rules-models-and-historical-similarity)
18. [Reports (HTML, PDF, JSON)](#18-reports-html-pdf-json)
19. [Users, SSO, and audit](#19-users-sso-and-audit)
20. [Supported file types and COMTRADE matrix](#20-supported-file-types-and-comtrade-matrix)
21. [Sample / test / golden data](#21-sample--test--golden-data)
22. [Engineering language used in reports](#22-engineering-language-used-in-reports)
23. [Frequently asked questions](#23-frequently-asked-questions)
24. [Troubleshooting](#24-troubleshooting)
25. [Where to find more documentation](#25-where-to-find-more-documentation)
26. [Quick reference card](#26-quick-reference-card)

---

## 1. What this tool is (and is not)

### What it is

An **engineering decision-support web application** that helps you:

- Create disturbance events and upload COMTRADE / ZIP packages / PDF attachments
- Detect and validate COMTRADE format, revision, container, encoding
- Stream and inspect waveforms (raw/scaled samples)
- Reconstruct an event timeline from analog/digital channels
- Evaluate protection element behaviour (including curve/zone physics where inputs exist)
- Run a **Protection Consistency Check** before RCA
- Classify faults when electrical evidence is sufficient
- Rank RCA hypotheses with supporting / contradicting / missing evidence
- Find historically similar events (supporting only)
- Generate controlled HTML / PDF / JSON reports
- Record engineer review (accept / modify / reject / inconclusive / field investigation)

### What it is not

| Not this | Why it matters |
|----------|----------------|
| Generative AI / ChatGPT / LLM | Conclusions are deterministic rules, calculations, and templates |
| Relay / breaker control | **Read-only.** No OT commands, no setting writes to IEDs |
| Automatic “relay malfunction” from one inconsistency | Stays **INCONSISTENT / INCONCLUSIVE** until settings are verified |
| Silent data repair | Malformed COMTRADE is flagged, not quietly fixed |
| Invented fault distance | Shows **NOT CALCULABLE** when CT/VT/line/settings are missing |

Always ask (the UI is designed around these):

1. **What happened?**  
2. **Why does the system think that?**  
3. **Which setting was used?**  
4. **What evidence supports it?**  
5. **What evidence contradicts it?**  
6. **What is uncertain?**  
7. **What should I verify?**

---

## 2. Starting and stopping the application

### Option A — Double-click launcher (recommended)

1. Open the project folder: `protection-rca` **or** the portable share folder (`portable-share`)
2. Double-click **`ProtectionRCA.exe`**
3. Wait until the browser opens:
   - **Portable mode** (when `frontend\dist\index.html` exists): `http://127.0.0.1:8001/`
   - **Dev mode** (no built UI yet): `http://127.0.0.1:5173/`
4. A small window appears: **“Protection RCA is running”** — it also lists **LAN URLs** for other PCs

**To stop everything:** close that window (or click **Stop & Close**).  
This shuts down the API and UI processes started by the launcher.

> Keep the control window open while you work. Closing a browser tab alone does **not** stop the services.

### Option B — Share with another person (no install on their PC)

Do **not** send only the `.exe`. Build a complete portable folder on your machine, then zip and send it.

```bat
cd protection-rca
scripts\build-portable-share.bat
```

That creates `protection-rca\portable-share\` containing:

| Item | Purpose |
|------|---------|
| `ProtectionRCA.exe` | Launcher |
| `backend\` (including `.venv`) | API + Python runtime — no separate Python install |
| `frontend\dist\` | Built web UI — no Node/npm install |
| `rules\` | RCA / protection rule catalogs |
| `HOW_TO_RUN.txt` | Short start / LAN instructions |

**On the other laptop:**

1. Unzip the folder anywhere (keep the internal structure).
2. Double-click `ProtectionRCA.exe`.
3. Browser opens `http://127.0.0.1:8001/`.
4. Close the control window to stop.

Windows 10/11 64-bit is required. Antivirus may scan the first launch — allow the app if prompted.

### Option C — Network access while you run it (LAN)

Use this when **your laptop hosts** the app and colleagues open it from their browsers on the **same Wi‑Fi / office LAN**.

1. Start `ProtectionRCA.exe` on the host laptop (portable mode preferred).
2. Read the **LAN URL** in the control window, for example: `http://192.168.1.50:8001/`
3. When Windows Firewall asks, **allow** access on **private** networks (port **8001**, or **5173** in pure Vite/dev mode).
4. Colleagues open that **LAN URL** in Chrome or Edge.

Important:

- Other PCs must **not** use `http://127.0.0.1:...` — that only works on the host.
- Use a **trusted LAN only** (not the public internet).
- Event data stays on the host PC (`backend\protection_rca_local.db` for local/portable runs).

### Option D — Scripts (developers)

```bat
cd protection-rca
scripts\start-all.bat
```

Or separately:

```bat
scripts\start-backend.bat
scripts\start-frontend.bat
```

To force Vite/dev UI even when `frontend\dist` exists:

```bat
set PROTECTION_RCA_DEV=1
ProtectionRCA.exe
```

| Service | Typical URL |
|---------|-------------|
| Web UI (portable) | http://127.0.0.1:8001 |
| Web UI (dev / Vite) | http://127.0.0.1:5173 |
| API docs | http://127.0.0.1:8001/docs |
| Health | http://127.0.0.1:8001/health |
| LAN (others) | `http://<your-PC-IP>:8001/` (portable) |

### Option E — Docker Compose (full stack)

```bash
cd protection-rca
docker compose up --build
```

Services typically include: frontend, backend, PostgreSQL, Redis/Celery worker, MinIO object storage.

Database migrations: Alembic revision `0001_initial_schema` creates the application schema. Local scripted runs may use SQLite (`protection_rca_local.db`); Compose uses PostgreSQL.

See `README.md` and `docs/DEPLOYMENT.md`.

### Folder layout reminder

`ProtectionRCA.exe` must stay **inside** the `protection-rca` folder **or** the `portable-share` folder so it can find:

- `backend/` (and `backend\.venv` for portable / local scripted runs)
- `frontend/` (portable needs `frontend\dist\`; dev may also use Node via `.tools\node\` or a system install)
- `rules/` (analysis catalogs)

Rebuild the launcher after launcher script changes:

```bat
scripts\build-launcher-exe.bat
```

---

## 3. Signing in (local and SSO)

### Local username / password

1. Open the UI.
2. Enter **Username** and **Password**.
3. Click **Sign in**.

There are **no demo events or demo assets** by default.

### Optional SSO (OIDC)

If the server is configured with `AUTH_MODE=oidc` and a valid issuer / client:

- The login page shows **Sign in with SSO (OIDC)**
- API exposes `GET /api/auth/mode` and `POST /api/auth/oidc/callback`
- First-time OIDC users are provisioned as **VIEWER** until an admin elevates the role

If OIDC is not configured, only local login is shown.

### First-time admin (empty database)

```bat
set BOOTSTRAP_ADMIN_USERNAME=admin
set BOOTSTRAP_ADMIN_PASSWORD=your-strong-password
set BOOTSTRAP_ADMIN_EMAIL=admin@example.com
```

Then launch the backend/exe again. This creates **only** an admin user — no sample substations or events.

### Sign out

Use **Sign out** in the top bar (user area).

---

## 4. Roles and permissions

| Role | Typical use |
|------|-------------|
| **VIEWER** | Read dashboards, events, reports |
| **ANALYST** | Create events, upload files, start analysis |
| **PROTECTION_ENGINEER** | Settings, consistency interpretation, review actions |
| **APPROVER** | Approvals, audit access |
| **ADMIN** | Users, rules/models administration |

Authorization is enforced on the server. If a button fails with “forbidden”, your role is insufficient.

---

## 5. Main navigation

Left sidebar is grouped:

### Operations

| Menu | Purpose |
|------|---------|
| **Dashboard** | KPI overview, trends, attention queue |
| **Events** | List / filter disturbance events |
| **Create event** | Guided multi-step wizard |
| **Upload** | Upload-centric entry for records |

### Plant

| Menu | Purpose |
|------|---------|
| **Assets / Substations / Bays / Relays / Breakers** | Plant topology |

### Engineering

| Menu | Purpose |
|------|---------|
| **Settings / Versions / Groups** | Setting hierarchy |
| **Rules** | Protection / consistency / RCA rule packages |
| **Models** | Classical ML model registry |

### Administration

| Menu | Purpose |
|------|---------|
| **Users** | Account administration |
| **Audit** | Audit trail |

### Help

In-app help and this user guide.

---

## 6. Dashboard (operations console)

The dashboard is the engineering operations console. It uses **live database values** — never fabricated demo events.

### Clickable KPI tiles

Each tile opens the Events list with the matching filter (`?queue=…`):

| KPI | Filter meaning |
|-----|----------------|
| Total Events | All events |
| Awaiting Analysis | Uploaded / queued / analysing |
| Awaiting Review | Analysed / review states |
| Completed Reports | Events with ready reports |
| Consistency Issues | Events with INCONSISTENT findings |
| High Severity Findings | HIGH / CRITICAL consistency |
| RCA Inconclusive | Decision INCONCLUSIVE / DATA_INSUFFICIENT |
| Parser / DQ Issues | WARNING / POOR / INVALID data quality |

### Event trend (7 / 30 / 90 days)

Stacked bars for **Analysed · Review · Issues**. Switch the window with the **7d / 30d / 90d** controls. Empty windows show a clear empty state.

### Data quality overview

Donut breakdown from actual event `data_quality` values:

- GOOD / ACCEPTABLE  
- WARNING / POOR / INVALID  
- UNSUPPORTED / NOT VALIDATED / Unknown  

Percentages are computed from real counts.

### Attention required

Prioritised list of events needing action (awaiting analysis/review, inconclusive RCA, DQ issues, high-severity consistency). Each row links into the event workspace.

### Recent events table

Columns include:

Event ID · Date/Time · Substation/Bay · Relay · Fault · Protection · Consistency · RCA · Status · Severity · DQ

### Empty database behaviour

When there are zero events:

- All counters show **0**
- Banner: “No disturbance events yet”
- Actions: **+ New event** · **Upload records**
- Recommended workflow checklist (Create → Upload → Validate → Analyse → Consistency → RCA → Report)

No fake demo events are seeded unless you explicitly enable a demo mode (not default).

---

## 7. Recommended workflow (end-to-end)

```text
1. Create Event          (/events/new wizard or Quick create)
2. Upload disturbance package (CFG+DAT / CFF + related files)
3. Confirm COMTRADE detection / validation
4. Start analysis
5. Inspect Waveforms + Timeline
6. Review Electrical + Protection
7. Study Consistency (setting source!)
8. Study RCA + Evidence (+ similar events if shown)
9. Download Report (HTML / PDF)
10. Complete Engineer Review
```

Do **not** skip Consistency when RCA looks “confident.” Consistency findings often explain why RCA must stay inconclusive.

---

## 8. Create Event wizard (guided)

Open **Operations → Create event** (route `/events/new`).

### Step 1 — Event information

| Field | Guidance |
|-------|----------|
| Event ID | Optional — auto-generated if blank |
| Substation / Bay / Feeder / Asset | Use known names; blanks stored as UNKNOWN / NOT VERIFIED |
| Relay / Breaker | Optional; prefer NOT VERIFIED over invented tags |
| Event Date/Time | Disturbance time if known |
| Nominal voltage / frequency | Only if verified |
| Description | Short factual note |

Never invent plant data.

### Step 2 — File upload

Drag-and-drop disturbance package. Supported extensions include  
`.cfg .dat .cff .hdr .inf .csv .txt .xml .json .pdf .zip`.

**ZIP packages:** uploading a `.zip` **auto-extracts** the archive. Each allowed member (COMTRADE, settings, SOE, PDF, etc.) is stored as its own immutable event file and used for detection, validation, and analysis. The original ZIP is kept as a **PACKAGE** attachment for evidence. Nested ZIPs are expanded (limited depth). Unsupported members are skipped (recorded in metadata). Path-traversal / zip-bomb guards apply.

### Step 3 — Detection

Automatic COMTRADE detection: status, revision, container, data format, encoding.  
If you uploaded a ZIP, detection runs on the **extracted** COMTRADE members.

### Step 4 — Validation

Validation status and data quality. Warnings are shown explicitly.

### Step 5 — Analysis

Click **Start analysis**. Open the event workspace to follow progress.

You can also use **Events → Quick create** for a shorter modal, or **Upload** to create an event from dropped files.

---

## 9. Uploading files

### From the event **Files** tab

1. Open the event → **Files**
2. Drag and drop, or use the file picker
3. Confirm upload
4. Note **SHA-256** (integrity / chain of custody)

Original files are stored **immutably** (content-addressed; not overwritten).

### From **Operations → Upload**

Drop files to create a new event in one step. Same extension rules and ZIP auto-extract behaviour apply.

### Deleting an event

On **Events** list → **Actions → Delete**, or open an event and use **Delete event** in the header. Requires **ANALYST** (or higher). Confirm the dialog — the event and related DB records are removed. Stored file blobs remain content-addressed (immutable storage); they are not rewritten.

### Good practice

- Upload **CFG + DAT** together (same base name when possible)
- For CFF, upload the `.cff`
- Or upload a **ZIP** containing CFG/DAT/CFF (+ settings / SOE / PDF) — members are extracted automatically
- Include settings exports / event reports / PDF attachments when available
- Prefer originals from relay software — do not re-save in Excel

---

## 10. COMTRADE detection and validation

Open the event → **COMTRADE** tab.

| Field | Example meaning |
|-------|-----------------|
| Standard / revision | IEEE C37.111 1991 / 1999 / 2013 · IEC 2001 / 2013 |
| Container | CFG+DAT or CFF |
| Data format | ASCII, BINARY, BINARY32, FLOAT32 |
| Status | SUPPORTED / PARTIALLY_SUPPORTED / UNSUPPORTED |
| Channels / sample rate | From CFG metadata |

Validation statuses:

| Status | Meaning |
|--------|---------|
| **VALID** | Checks passed |
| **VALID_WITH_WARNINGS** | Usable — review warnings |
| **PARTIALLY_SUPPORTED** | Some features not fully validated (e.g. IEEE 1991 partial) |
| **NOT_VALIDATED** | Could not fully validate |
| **INVALID** | Do not trust results; fix source data |

The system does **not** silently interpolate missing samples or invent channels.

---

## 11. Running analysis

1. After upload/validation, start analysis (wizard Step 5 or event workspace)
2. Watch **Analysis progress** and the **status bar** lamps:

```text
COMTRADE · DATA · SETTINGS · PROTECTION · CONSISTENCY · RCA · REPORT
```

Pipeline stages:

```text
Upload → File Detection → COMTRADE Validation → Parsing →
Signal Processing → Event Reconstruction → Protection Analysis →
Consistency Checker → Fault Classification → RCA → Evidence → Report
```

Stage icons: ✓ completed · ● running · ○ pending · ✕ failed

On parse/analyse the platform:

- Persists COMTRADE file/channel metadata
- Caches waveform samples for the Waveforms tab
- Runs consistency and RCA engines
- Indexes classical similarity features
- Can generate an HTML report artefact

Typical local analysis for normal records targets **under ~2 minutes**.

---

## 12. Event analysis workspace (detailed)

Event header shows: **Event ID · Substation · Bay · Relay · Date/Time** plus status / DQ / decision badges.

### Overview

Five engineering panels:

1. **What happened** — fault, inception, protection, consistency, RCA, DQ  
2. **Why** — primary hypothesis with links to Evidence / RCA  
3. **Which setting** — source, version, group, active group verification  
4. **What is uncertain** — missing evidence, unverified settings, DQ, inconclusive items  
5. **What should I verify** — deterministic recommended actions  

Fault distance shows **NOT CALCULABLE** when inputs are missing (never invented).

### Files

Uploaded originals, hashes, sizes, types.

### COMTRADE

Detection, validation, channel counts, sample rates, parser version.

### Waveforms

Interactive viewer with **real sample arrays** (from analysis cache / on-demand parse):

- Zoom / pan / cursors  
- Channel selection · analog/digital  
- Markers when available  
- Engineering units  

Inspect individual sample values — not smoothed-only curves.

### Timeline

Chronological reconstruction (inception → pickup → trip → breaker → interruption → reclose/lockout when evidence exists). Missing signals → **NOT AVAILABLE**.

### Electrical

RMS, phasors, sequences, power, impedance, etc., each with method/quality. Missing → **NOT CALCULABLE**.

### Protection

Per-element table: Enabled · Pickup · Trip · Expected · Timing · Consistency · Setting source · Evidence.

See also [§13 Protection physics](#13-protection-physics-51-and-21).

### Consistency (critical)

Always read:

- Overall status  
- Setting source / version  
- Active setting group (**NOT VERIFIED** if unknown)

| Status | Meaning |
|--------|---------|
| CONSISTENT | Observed matches expected under referenced settings |
| INCONSISTENT | Conflict — investigate; do **not** auto-confirm relay malfunction |
| UNVERIFIABLE | Cannot decide with available inputs |
| DATA_QUALITY_ISSUE | Record quality blocks the check |

**Mandatory rule:** `51 Enabled = FALSE` with pickup/trip observed → **INCONSISTENT** (typically HIGH). RCA remains **INCONCLUSIVE** regarding relay malfunction until active configuration is verified.

### RCA

Hypothesis board with status CONFIRMED / PROBABLE / POSSIBLE / UNLIKELY / INCONCLUSIVE, score, supporting / contradicting / missing evidence.

**CONFIRMED** only when evidence requirements are met. Similarity and ML are supporting only.

### Evidence

```text
RCA → Hypothesis → Finding → Calculation → Source → Raw data / file
```

### Report

See [§18 Reports](#18-reports-html-pdf-json).

### Review

| Action | When to use |
|--------|-------------|
| **ACCEPT** | Agree with automated findings |
| **MODIFY** | Accept with documented corrections |
| **REJECT** | Reject automated conclusions |
| **INCONCLUSIVE** | Cannot close with available evidence |
| **REQUEST FIELD INVESTIGATION** | Need field verification |

Automated results are retained; overrides are audited separately.

---

## 13. Protection physics (51 and 21)

### Element 51 — time overcurrent

When pickup current, time dial (TMS), curve type, and measured current are available, the engine computes expected operate time using IEC/IEEE inverse curves, for example:

- IEC Normal / Very / Extremely / Long-time Inverse  
- IEEE Moderately / Very / Extremely Inverse  

Formula family: `t = TDS × (A / (M^p − 1) + B)` for multiple `M > 1`.

If inputs are missing → timing physics status **NOT_CALCULABLE** (stated in timing metadata). Observed vs expected timing may raise inconsistency when both exist and the error exceeds configured tolerance.

### Element 21 — distance

When apparent impedance and zone reach settings exist, a deterministic **mho** (default) or simple **quad** reach check evaluates zone entry.

If impedance or reach is missing → **NOT_CALCULABLE** / fault distance not invented.

---

## 14. Understanding status badges and quality labels

### Decision states

ANALYSIS_COMPLETE · ANALYSIS_COMPLETE_WITH_WARNINGS · INCONCLUSIVE · DATA_INSUFFICIENT · UNSUPPORTED_FORMAT · ENGINEER_REVIEW_REQUIRED

### Data quality

GOOD → ACCEPTABLE → WARNING → POOR → INVALID (+ NOT VALIDATED / UNSUPPORTED)

### Consistency

CONSISTENT · INCONSISTENT · UNVERIFIABLE · DATA_QUALITY_ISSUE

### Severity

INFO · LOW · MEDIUM · HIGH · CRITICAL

### Honest engineering labels

| Label | Meaning |
|-------|---------|
| NOT AVAILABLE | Signal/result absent |
| NOT VERIFIED | Setting group / source not independently verified |
| NOT VALIDATED | Format/feature not validated |
| NOT CALCULABLE | Missing inputs (e.g. distance) |
| INCONCLUSIVE | Evidence does not support confirmation |
| ML RESULT: NOT AVAILABLE | No approved classical ML model |
| SIMILARITY: NOT AVAILABLE | No comparable historical features yet |

---

## 15. Settings and setting hierarchy

Navigate: **Settings** → Overview / Versions / Groups.

Priority (highest first):

1. Event-specific active setting  
2. Active setting group  
3. Approved relay base setting  
4. Relay configuration  
5. Historical setting  
6. Engineering design setting  

The UI shows which source was used. The system **never silently picks** a group without displaying it.

If active group cannot be established → **Relay Base Settings** as first-level reference and active group **NOT VERIFIED**.

---

## 16. Assets (substations, bays, relays, breakers)

1. Create **Substation**  
2. Create **Bay**  
3. Register **Relay** and **Breaker**  
4. Link events when known  

Unknown at event time → leave blank; update later. Wizard free-text labels are stored as plant labels (UNKNOWN / NOT VERIFIED) until assets are registered.

---

## 17. Rules, models, and historical similarity

### Rules

Versioned packages (protection, consistency, RCA, fault). Activated versions apply to new analyses. Versions are stored with analysis for reproducibility.

### Models

Classical ML governance only (XGBoost / sklearn-class models if approved). No generative AI. Unapproved → **ML RESULT: NOT AVAILABLE**. ML never overrides deterministic evidence.

### Historical similarity

After analysis, classical feature vectors (voltage, frequency, DQ, fault/status hashes) are compared with cosine similarity.

- Displayed as **supporting evidence only**  
- Never treated as proof of root cause  
- Optional future pgvector ANN index; classical path works on SQLite and PostgreSQL today  

---

## 18. Reports (HTML, PDF, JSON)

Open event → **Report**.

| Format | How to get it |
|--------|----------------|
| **JSON** | Structured sections in the report record |
| **HTML** | **Download HTML** — Jinja controlled templates / deterministic fallback |
| **PDF** | **Download PDF** — ReportLab packaging of the engineering content |

API:

- `POST /api/reports` with `format`: `JSON` | `HTML` | `PDF`  
- `GET /api/reports/{id}/download`  

Report statements distinguish **OBSERVED / CALCULATED / INFERRED / HYPOTHESIS**. Every conclusion must be traceable to structured data — no LLM prose.

Print remains available via the browser print dialog.

---

## 19. Users, SSO, and audit

### Users

Admins manage accounts and roles under **Users**.

### SSO

See [§3](#3-signing-in-local-and-sso). Configure `AUTH_MODE`, `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_AUDIENCE` on the backend.

### Audit

Examples of audited actions:

- Login (local or OIDC)  
- Upload  
- Analysis start / complete  
- Setting create / modify  
- Report generate / download  
- Engineer review / approval  
- Manual override  

Each entry: who / when / what / old→new where applicable.

---

## 20. Supported file types and COMTRADE matrix

| Extension | Typical content |
|-----------|-----------------|
| `.cfg` / `.dat` | COMTRADE configuration + data |
| `.cff` | Combined COMTRADE file |
| `.hdr` / `.inf` | Header / information |
| `.csv` / `.txt` | SOE / reports (when parsers exist) |
| `.xml` / `.json` | Settings / configuration exports |
| `.pdf` | Supporting attachment (reports, drawings, notes) — stored, not parsed as COMTRADE |
| `.zip` | Package archive — **auto-extracted**; allowed members processed further; ZIP kept as PACKAGE |

Detection prefers **file contents**, not extension alone.

Supported / regression-covered families (see `docs/COMTRADE_SUPPORT.md` for partial notes):

| Variant | Notes |
|---------|-------|
| IEEE C37.111-1999 / 2013 | Primary |
| IEEE C37.111-1991 | Partial support — fixtures included |
| IEC 60255-24:2001 / 2013 | Via aliases / detectors |
| ASCII · BINARY · BINARY32 · FLOAT32 | Parsers + golden fixtures |
| CFF | Detect / unpack path + fixture |

---

## 21. Sample / test / golden data

For training or regression (not production events):

```text
test_data/comtrade/ieee_1999/ag_fault.cfg|.dat
test_data/comtrade/ieee_2013/mixed_event.cfg|.dat
test_data/comtrade/ieee_1991/ag_fault.cfg|.dat
test_data/comtrade/ieee_binary/
test_data/comtrade/ieee_binary32/
test_data/comtrade/ieee_float32/
test_data/comtrade/cff/ag_fault.cff
test_data/comtrade/malformed/
test_data/golden/
```

Regenerate synthetic matrix fixtures:

```bat
cd protection-rca
python scripts\generate_comtrade_fixtures.py
```

Create a **new empty event**, upload files, run analysis, and explore each tab.

---

## 22. Engineering language used in reports

Controlled templates only. Examples:

- OBSERVED: trip digital was present  
- CALCULATED: apparent impedance entered Zone 1 reach  
- INFERRED: operation consistent with configured reach  
- HYPOTHESIS: internal feeder fault is probable  

Never treat fluent wording as stronger than status badges.

---

## 23. Frequently asked questions

**Q: Why are Location / Relay / Fault columns empty?**  
A: No analysis yet, or names not linked. Complete Files → Analysis, or fill wizard labels.

**Q: Why is RCA INCONCLUSIVE?**  
A: Consistency findings (e.g. disabled 51 operating), unverified setting group, or missing evidence for CONFIRMED.

**Q: Can the tool trip a breaker or change settings?**  
A: No. OT control is disabled.

**Q: Does it use ChatGPT?**  
A: No.

**Q: Fault distance NOT CALCULABLE**  
A: Needs validated CT/VT, line parameters, and impedance model — never invented.

**Q: Waveforms empty**  
A: Run analysis after upload so samples are parsed and cached; check COMTRADE validation.

**Q: How do I get a PDF?**  
A: Event → Report → **Download PDF**.

**Q: Can I upload a ZIP of CFG/DAT?**  
A: Yes. The ZIP is auto-extracted; COMTRADE/settings/SOE/PDF members are stored and used in detect → validate → analysis. The original ZIP remains as evidence.

**Q: Can I delete an event?**  
A: Yes — Events list **Delete**, or event header **Delete event** (ANALYST+). Confirm first.

**Q: KPI click does nothing useful**  
A: It filters Events by queue. Use **Clear filter** to reset.

**Q: SSO button missing**  
A: OIDC not enabled on the API (`AUTH_MODE` still `local`).

**Q: Closed browser but ports busy**  
A: Close the launcher control window (**Stop & Close**).

**Q: Can I give only ProtectionRCA.exe to a colleague?**  
A: No. They need the full **`portable-share`** folder (exe + `backend` + `frontend\dist` + `rules`). Build it with `scripts\build-portable-share.bat`.

**Q: How do others open the app from my laptop?**  
A: Start the exe on your PC, allow Firewall if asked, then they open the **LAN URL** shown in the control window (e.g. `http://192.168.x.x:8001/`). Do not share `127.0.0.1` with them.

**Q: Browser opens 8001 or 5173 — which is correct?**  
A: **8001** = portable (built UI served with the API). **5173** = developer Vite UI. Both use API on **8001**.

---

## 24. Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Exe says backend/frontend not found | Run `ProtectionRCA.exe` from inside `protection-rca` or `portable-share` |
| UI blank / API errors | http://127.0.0.1:8001/health |
| Port in use | Portable UI+API: **8001**; Vite UI: **5173** |
| Colleague cannot open LAN URL | Same Wi‑Fi/LAN; use host IP not 127.0.0.1; allow Windows Firewall private network for port **8001** |
| Exe rebuild “Access denied” | Close running `ProtectionRCA.exe`, then run `scripts\build-launcher-exe.bat` again |
| Upload rejected | Extension, size limit, or role |
| COMTRADE INVALID | Fix source export; do not force confident RCA |
| Analysis stuck | Progress stage + API logs; re-upload CFG+DAT |
| Waveforms empty | Analysis/parse not run or validation failed |
| Consistency empty | Analysis not run or no digital/setting inputs |
| PDF download fails | Ensure `reportlab` installed in backend env |
| Cannot review | Role below PROTECTION_ENGINEER / APPROVER |

API docs: http://127.0.0.1:8001/docs

---

## 25. Where to find more documentation

| Document | Content |
|----------|---------|
| `README.md` | Install, launch, overview |
| `docs/IMPLEMENTATION_STATUS.md` | Honest feature status vs specification |
| `docs/ARCHITECTURE.md` | System design |
| `docs/API.md` | REST endpoints |
| `docs/COMTRADE_SUPPORT.md` | Format support matrix |
| `docs/PROTECTION_RULES.md` | Protection rule engine |
| `docs/CONSISTENCY_CHECKER.md` | Consistency logic |
| `docs/RCA_ENGINE.md` | Hypothesis scoring |
| `docs/ENGINEERING_LIMITATIONS.md` | Explicit non-claims |
| `docs/SECURITY.md` | Auth, RBAC, OT read-only |
| `docs/TESTING.md` | Tests / golden data |
| `docs/DEPLOYMENT.md` | Docker / AWS notes |
| `docs/DATABASE.md` | Schema notes |

Word copies of this guide:

- `docs/Protection_RCA_User_Guide.docx`  
- `docs/Protection_RCA_User_Guide.doc`  
- Project root copies with the same names  

Regenerate Word files after editing this Markdown:

```bat
cd protection-rca
python scripts\export_user_guide_doc.py
```

---

## 26. Quick reference card

```text
START     → Double-click ProtectionRCA.exe (portable: :8001 · dev: :5173)
STOP      → Close launcher control window
SHARE     → scripts\build-portable-share.bat → zip portable-share\
LAN       → Others open http://<host-IP>:8001/ (Firewall allow)
LOGIN     → Local account or SSO (if configured)
NEW WORK  → Create event wizard → upload CFG/DAT/CFF (or ZIP)
ANALYSE   → Start analysis → watch status bar + progress
VERIFY    → Waveforms → Timeline → Consistency → RCA → Evidence
REPORT    → Download HTML or PDF
CLOSE-OUT → Review (ACCEPT / MODIFY / REJECT / …)
DELETE    → Events Actions → Delete (ANALYST+)
REMEMBER  → No invented data · No OT control · No generative AI
```

---

*End of User Guide — Protection RCA Platform (document version 0.3.0)*
