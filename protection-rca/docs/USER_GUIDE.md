# Protection RCA — User Guide

**Audience:** Protection engineers, analysts, approvers, and administrators  
**Product:** Protection Disturbance Record (DR) / COMTRADE analysis and Root Cause Analysis (RCA) platform  
**Document version:** 0.6.0  
**Application:** Protection RCA web application (React + FastAPI)

This guide explains how to launch the application, build the plant hierarchy, upload and analyse disturbance events under each IED, interpret results, generate reports, and complete engineer review. It reflects the **current implemented behaviour** of the platform.

---

## Document revision — what is covered in this edition

This edition (**0.6.0**) documents the **plant-first** workflow and related UI/ops upgrades:

| Area | What changed |
|------|----------------|
| **Plant-first workflow** | **No direct Create event / Upload** entry points. Build **Substation → Voltage level → Bay → Feeder → IED**, then open the IED to upload COMTRADE / packages |
| **Plant hierarchy UI** | Full-width Plant page: step strip, count tiles, expandable tree with **+ Voltage / + Bay / + Feeder / + IED**, **Open** on each IED, Delete at every level |
| **IED workspace** | Per-IED page: upload disturbance records, list events for that relay, open analysis |
| **All events** | Global list with live **Search** (ID, station, bay, relay, fault/protection, status, DQ) and **From / To** date filters; shows “X of Y events”; **Clear filters** |
| **Protection column** | Events / Dashboard show operated elements (e.g. **51N, 87T, 21**) plus fault type where known |
| **Dashboard layout** | Full-width operations console: Work inbox, **Operations** + **Quality & findings** KPI rows (4×2), trend chart + Attention queue + DQ donut, Recent events with compact badges |
| **Navigation** | Sidebar: **Plant** · **Analysis** (Dashboard, All events) · **Administration** (Users, Audit) · **Help** |
| **Dual SQLite DBs** | **Users/passwords** in `backend\protection_rca_auth.db`; **plant + events** in `backend\protection_rca_local.db`. Clearing plant/events does **not** wipe logins |
| **Default bootstrap admin** | Fresh install: **`admin` / `admin123`** (change in production) |
| **Continue last event** | Dashboard / All events **Continue** uses local recent-event memory; pruned when events are deleted or the DB is empty |

Earlier **0.5.0** coverage (still valid — engineering analysis features):

| Area | What changed |
|------|----------------|
| **R–X locus** | Faulted loop only; RIO/XRIO trip zones when settings provide them |
| **Impedance / harmonics / Id–Ir** | Faulted-loop Z table; harmonics heatmap; 87 operate/restraint when both-side currents exist |
| **87T through-fault / CT sat** | Through-fault exclusion paths; phase-current-only soft CT-sat cues |
| **Decision badges** | CONFIRMED → `ANALYSIS_COMPLETE` unless material warnings; PROBABLE → WITH_WARNINGS |
| **Settings auto-approve** | Uploaded settings APPROVED / active group VERIFIED by default |
| **Portable build / LAN** | `build-portable-share.bat`, single-port **8001** portable mode, LAN URLs in launcher |
| **Event workspace** | Tab groups Setup · Analyse · Protect · Conclude; Channel map; DR targets; background analysis |
| **Scheme library / cause enrichment** | Scheme-aware RCA; field/asset cause checkboxes on RCA page |
| **Reports / safety** | HTML + PDF + JSON; no generative AI; no OT control |

---

## Table of contents

1. [What this tool is (and is not)](#1-what-this-tool-is-and-is-not)
2. [Starting and stopping the application](#2-starting-and-stopping-the-application)
3. [Signing in (local and SSO)](#3-signing-in-local-and-sso)
4. [Roles and permissions](#4-roles-and-permissions)
5. [Main navigation](#5-main-navigation)
6. [Dashboard (operations console)](#6-dashboard-operations-console)
7. [Recommended workflow (end-to-end)](#7-recommended-workflow-end-to-end)
8. [Plant hierarchy (create structure + upload on IED)](#8-plant-hierarchy-create-structure--upload-on-ied)
9. [All events (list and filters)](#9-all-events-list-and-filters)
10. [Uploading files](#10-uploading-files)
11. [COMTRADE detection and validation](#11-comtrade-detection-and-validation)
12. [Running analysis](#12-running-analysis)
13. [Event analysis workspace (detailed)](#13-event-analysis-workspace-detailed)
14. [Protection physics and schemes](#14-protection-physics-and-schemes)
15. [Understanding status badges and quality labels](#15-understanding-status-badges-and-quality-labels)
16. [Settings and setting hierarchy](#16-settings-and-setting-hierarchy)
17. [Databases (auth vs plant/events)](#17-databases-auth-vs-plantevents)
18. [Rules, models, and historical similarity](#18-rules-models-and-historical-similarity)
19. [Reports (HTML, PDF, JSON)](#19-reports-html-pdf-json)
20. [Users, SSO, and audit](#20-users-sso-and-audit)
21. [Supported file types and COMTRADE matrix](#21-supported-file-types-and-comtrade-matrix)
22. [Sample / test / golden data](#22-sample--test--golden-data)
23. [Engineering language used in reports](#23-engineering-language-used-in-reports)
24. [Frequently asked questions](#24-frequently-asked-questions)
25. [Troubleshooting](#25-troubleshooting)
26. [Where to find more documentation](#26-where-to-find-more-documentation)
27. [Quick reference card](#27-quick-reference-card)

---

## 1. What this tool is (and is not)

### What it is

An **engineering decision-support web application** that helps you:

- Build a **plant hierarchy** (Substation → Voltage → Bay → Feeder → IED) and upload COMTRADE / ZIP / vendor packages / PDF **on each IED**
- Detect and validate COMTRADE format, revision, container, encoding
- Map analog channels and digital DR targets (pickup/trip/52a/…)
- Stream and inspect waveforms (raw/scaled samples)
- Reconstruct an event timeline from analog/digital channels (+ SOE when available)
- Evaluate protection element behaviour and scheme context (including curve/zone physics where inputs exist)
- Run a **Protection Consistency Check** before RCA
- Classify faults when electrical evidence is sufficient
- Rank RCA hypotheses with supporting / contradicting / missing evidence (+ engineer cause enrichment)
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
- Event data stays on the host PC:
  - Plant + events: `backend\protection_rca_local.db`
  - Users / passwords: `backend\protection_rca_auth.db`

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

Database migrations: Alembic revision `0001_initial_schema` creates the application schema. Local scripted / portable runs use **two SQLite files** (see [§17](#17-databases-auth-vs-plantevents)); Compose uses PostgreSQL for application data.

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

**Default bootstrap account** (empty auth database / first launch):

| Field | Value |
|-------|--------|
| Username | `admin` |
| Password | `admin123` |

Change this password in production. There are **no demo events or demo plant assets** by default.

### Optional SSO (OIDC)

If the server is configured with `AUTH_MODE=oidc` and a valid issuer / client:

- The login page shows **Sign in with SSO (OIDC)**
- API exposes `GET /api/auth/mode` and `POST /api/auth/oidc/callback`
- First-time OIDC users are provisioned as **VIEWER** until an admin elevates the role

If OIDC is not configured, only local login is shown.

### First-time admin (custom bootstrap)

Override defaults before first launch:

```bat
set BOOTSTRAP_ADMIN_USERNAME=admin
set BOOTSTRAP_ADMIN_PASSWORD=your-strong-password
set BOOTSTRAP_ADMIN_EMAIL=admin@example.com
```

Then launch the backend/exe again. This creates **only** an admin user in the **auth** database — no sample substations or events.

### Sign out

Use **Sign out** in the top bar (user area).

---

## 4. Roles and permissions

| Role | Typical use |
|------|-------------|
| **VIEWER** | Read dashboards, events, reports |
| **ANALYST** | Build plant, upload on IED, start analysis |
| **PROTECTION_ENGINEER** | Settings, consistency interpretation, review actions |
| **APPROVER** | Approvals, audit access |
| **ADMIN** | Users, rules/models administration |

Authorization is enforced on the server. If a button fails with “forbidden”, your role is insufficient.

---

## 5. Main navigation

Left sidebar (plant-first):

### Plant

| Menu | Purpose |
|------|---------|
| **Plant** | Build and browse hierarchy: Substation → Voltage → Bay → Feeder → IED; open IED to upload |

### Analysis

| Menu | Purpose |
|------|---------|
| **Dashboard** | Work inbox, KPIs, trend, attention queue, recent events |
| **All events** | Global list with search + date filters; Compare; Continue last event |

### Administration

| Menu | Purpose |
|------|---------|
| **Users** | Account administration |
| **Audit** | Audit trail |

### Help

In-app help and this user guide.

> **Removed from the sidebar (by design):** standalone **Create event** and **Upload** pages. Creating records always goes through **Plant → IED → upload**. Old `/events/new` and upload-only routes redirect to **Plant**.

---

## 6. Dashboard (operations console)

The dashboard is the engineering operations console. It uses **live database values** — never fabricated demo events. Layout is **full width** of the main content area (sidebar to right edge).

### Work inbox

Top banner summarises items needing attention (analyse · review · consistency · high severity) with quick buttons:

- **Review queue**
- **Consistency**
- **Analyse**

Recent locally opened events appear as quick links. **Continue \<event id\>** jumps back into the last worked event (stored in browser memory; cleared when that event is deleted or the events DB is empty).

Header actions: **Continue** · **Compare** · **All events** · **Open Plant**.

### Clickable KPI tiles (two groups)

Each tile opens **All events** with the matching filter (`?queue=…`):

**Operations**

| KPI | Filter meaning |
|-----|----------------|
| Total Events | All events |
| Awaiting Analysis | Uploaded / queued / analysing |
| Awaiting Review | Analysed / review states |
| Completed Reports | Events with ready reports |

**Quality & findings**

| KPI | Filter meaning |
|-----|----------------|
| Consistency Issues | Events with INCONSISTENT findings |
| High Severity Findings | HIGH / CRITICAL consistency |
| RCA Inconclusive | Decision INCONCLUSIVE / DATA_INSUFFICIENT |
| Parser / DQ Issues | WARNING / POOR / INVALID data quality |

### Event trend (7 / 30 / 90 days)

Stacked bars for **Analysed · Review · Issues**. Switch the window with **7d / 30d / 90d**. Leading empty days are trimmed so sparse data stays readable.

### Attention required + Data quality

Right-hand stack:

1. **Attention required** — prioritised events (awaiting review/analysis, DQ, high severity, inconclusive). Each row links into the event workspace.
2. **Data quality overview** — donut from real `data_quality` counts (GOOD / ACCEPTABLE / WARNING / POOR / INVALID / …).

### Recent events table

Columns:

Event ID · Date/Time · Substation/Bay · Relay · Fault · **Protection** (e.g. 51N, 87T) · Consistency · RCA · Status · Severity · DQ

Status badges use short labels on this table (e.g. Complete, Review) — hover for the full glossary text.

### Empty database behaviour

When there are zero events:

- All counters show **0**
- Banner: “No disturbance events yet”
- Action: **Open Plant**
- Checklist: Build Plant (SS → kV → Bay → Feeder → IED) → Upload on IED → Validate → Analyse → Consistency → RCA → Report

No fake demo events are seeded unless you explicitly enable a demo mode (not default).

---

## 7. Recommended workflow (end-to-end)

```text
1. Open Plant                 (/plant)
2. Create Substation
3. Add Voltage level (e.g. 132kV)
4. Add Bay (e.g. Bay 1 / line1 bay)
5. Add Feeder
6. Add IED (relay)            → Open IED
7. Upload disturbance package on the IED (CFG+DAT / CFF / ZIP / vendor)
8. Confirm COMTRADE detection / validation
9. Setup → Channel map + DR targets (correct if auto-infer looks wrong)
10. Start / Re-run analysis (background — watch status bar)
11. Inspect DR workspace / Waveforms / Sequence
12. Review Electrical + Fault + Location + Protection
13. Study Consistency (setting source!)
14. Study RCA + Evidence (+ cause enrichment if field evidence exists)
15. Download Report (HTML / PDF)
16. Complete Engineer Review
```

Do **not** skip Consistency when RCA looks “confident.” Consistency findings often explain why RCA must stay inconclusive.

After changing **Channel map**, **DR targets**, settings, or **cause evidence**, always **Re-run analysis** so timeline, protection, consistency, and RCA refresh.

Use **All events** for a global view and filters; use **Plant → IED** for uploads scoped to the correct relay.

---

## 8. Plant hierarchy (create structure + upload on IED)

Open **Plant** in the sidebar (route `/plant`).

### Hierarchy levels

```text
Substation
  └── Voltage level (e.g. 132kV)
        └── Bay (e.g. Bay 1)
              └── Feeder
                    └── IED (relay)  ← upload + events live here
```

| Level | How to create | Notes |
|-------|---------------|--------|
| **Substation** | **+ Substation** (page header) | Top of the tree |
| **Voltage** | On a substation row → **+ Voltage** | Optional nominal kV |
| **Bay** | On a voltage row → **+ Bay** | Name the bay clearly (e.g. `line1 bay`) |
| **Feeder** | On a bay row → **+ Feeder** | |
| **IED** | On a feeder row → **+ IED** | Relay / IED name; becomes upload target |

Each row supports **Delete** (removes children too — confirm carefully). Expand/collapse with the tree twisty.

Count tiles at the top show totals: Substations · Voltage levels · Bays · Feeders · IEDs.

### Open an IED (workspace)

On an IED row click **Open** (or the IED name link). The **IED workspace** shows:

- Plant path context (substation / voltage / bay / feeder / IED)
- **Upload** disturbance record package for **this** IED only
- List of events already attached to this IED
- Links into each event’s analysis workspace

Events are always created with a **relay_id** (IED). There is no “orphan” upload path in the current UI.

### Naming tips

- Use site names operators recognise (`Substation 2`, `132kV`, `Bay 1`, `Feeder 1`, `IED-4`)
- Prefer verified tags over placeholders; you can still rename later by recreating or updating via admin APIs if needed
- Never invent plant topology that does not exist on site

---

## 9. All events (list and filters)

Open **Analysis → All events** (route `/events`).

### Header actions

| Control | Purpose |
|---------|---------|
| **Continue …** | Resume last locally remembered event |
| **Open Plant** | Go to hierarchy / upload |
| **Compare** | Multi-event compare |
| **Clear filters** | Clears search, dates, and dashboard `?queue=` filter |

When you arrive from a Dashboard KPI, a banner shows the active **queue filter** (e.g. Awaiting review).

### Search (live)

Type in **Search**. Matching is case-insensitive across:

- Event ID  
- Substation / bay / relay (IED)  
- Feeder / description  
- Fault type and **protection summary** (e.g. `87T`, `51N`)  
- Status, decision state, data quality, severity  

The counter shows **“X of Y events”**.

### Date range (From / To)

- Uses the event date/time (falls back to created time if needed)
- Times are interpreted in **local** browser time (no accidental UTC day-shift)
- If **To** is left at midnight (`00:00`), the filter includes the **entire calendar day**

### Table columns

Event ID · Date/Time · Location (substation + bay) · Relay · **Fault / element** (protection primary, fault type secondary) · Status · Sev · DQ · **Delete**

### Empty / no-match states

| Situation | Message |
|-----------|---------|
| No events in database | Prompt to open Plant and upload on an IED |
| Events exist but filters exclude all | “No events match…” + **Clear filters** |

---

## 10. Uploading files

### From the IED workspace (primary path)

1. **Plant** → expand to the IED → **Open**
2. Drag and drop (or file picker) the disturbance package
3. Confirm upload — event is created under that IED
4. Note **SHA-256** on the event **Files** tab (integrity / chain of custody)

Original files are stored **immutably** (content-addressed; not overwritten).

### From the event **Files** tab

After the event exists:

1. Open the event → **Files**
2. Drag and drop additional members (settings, SOE, PDF, …)
3. Confirm upload

### Supported extensions

`.cfg .dat .cff .hdr .inf .csv .txt .xml .json .pdf .zip`  
plus vendor / settings packages:  
`.set .rdb .xrio .rio .eve .cev .log .dz5 .dex5 .d5z .pcmi .pcmp`.

**ZIP packages:** uploading a `.zip` **auto-extracts** the archive. Each allowed member is stored as its own immutable event file. The original ZIP is kept as a **PACKAGE** attachment. Nested ZIPs expand (limited depth). Path-traversal / zip-bomb guards apply.

**Vendor notes (honest):**

| Format | Behaviour |
|--------|-----------|
| SEL `.rdb` | OLE container — SET_ALL text extracted when present → settings ingest |
| SEL `.cev` | Converted to CFG+DAT for waveform / timeline use when convertible |
| DIGSI / PCM600 `.dz5` / `.dex5` / `.d5z` / `.pcmi` / `.pcmp` | Treated as ZIP-like packages when they contain nested COMTRADE / settings / CEV; proprietary non-ZIP blobs stay **NOT CALCULABLE** with export guidance |
| `.set` / `.xrio` / `.rio` / `.eve` / `.log` / SOE CSV | Parsed when structure is recognized; RIO/XRIO supply distance trip-zone geometry for R–X when present |

### Deleting an event

On **All events** → **Delete**, or open an event and use **Delete event** in the header. Requires **ANALYST** (or higher). Confirm the dialog — the event and related DB records are removed. Stored file blobs remain content-addressed (immutable storage); they are not rewritten. Browser “Continue” memory for that event is cleared.

### Good practice

- Upload **CFG + DAT** together (same base name when possible)
- For CFF, upload the `.cff`
- Or upload a **ZIP** / vendor package containing CFG/DAT/CFF (+ settings / SOE / PDF)
- Upload under the **correct IED** so location / relay columns stay accurate
- After upload, confirm **Channel map** and **DR targets** before trusting protection timing
- Prefer originals from relay software — do not re-save in Excel

---

## 11. COMTRADE detection and validation

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

## 12. Running analysis

1. After upload/validation (and preferably after Channel map / DR targets), start analysis from the event workspace (**Start analysis** / **Re-run analysis**)
2. The API **queues** the job and returns immediately — engineering runs in the **background** so the browser does not time out
3. Watch **Analysis progress** and the **status bar** lamps:

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
- Applies channel map + digital (DR target) map to electrical / timeline / protection
- Runs consistency and RCA engines (scheme-aware where elements operate)
- Indexes classical similarity features
- Can generate an HTML report artefact

**Recommended next step** banner on the workspace guides the engineer (e.g. fix channel map, re-run after FAILED, open DR workspace).

If status is **FAILED**:

- Hover the FAILED badge or open **Details** for the job `error_message`
- Fix COMTRADE / channel map / DR targets / files as indicated
- Click **Re-run analysis**
- Prior results may still be viewable until the new run completes

Typical local analysis for normal records targets **under ~2 minutes**.

---

## 13. Event analysis workspace (detailed)

Event header shows: **Event ID · Substation · Bay · Relay · Date/Time** plus status / DQ / decision badges.

Tabs are grouped:

| Group | Tabs |
|-------|------|
| **Setup** | Overview · Files · COMTRADE · Channel map · DR targets |
| **Analyse** | DR workspace · Waveforms · Sequence · Electrical · Fault · Location |
| **Protect** | Protection · Consistency · RCA · Evidence |
| **Conclude** | Summary · Report · Review |

### Overview

Five engineering panels:

1. **What happened** — fault, inception, protection, consistency, RCA, DQ  
2. **Why** — primary hypothesis with links to Evidence / RCA  
3. **Which setting** — source, version, group, active group verification  
4. **What is uncertain** — missing evidence, unverified settings, DQ, inconclusive items  
5. **What should I verify** — deterministic recommended actions  

Plant labels (substation / bay / relay) and bay one-line context can be saved from Overview. Fault distance shows **NOT CALCULABLE** when inputs are missing (never invented).

### Files

Uploaded originals, hashes, sizes, types (including extracted ZIP / vendor members).

### COMTRADE

Detection, validation, channel counts, sample rates, parser version.

### Channel map

Assign analog channel **roles** (phase currents/voltages, neutral, etc.). Wrong roles produce wrong RMS/phasors/impedance — fix here, then **re-run analysis**.

### DR targets (digital map)

Map digital channels to protection roles:

| Role | Typical use |
|------|-------------|
| **PICKUP** | Element pickup assert |
| **TRIP** | Trip / operate assert |
| **52A** / **52B** | Breaker auxiliary |
| **RECLOSE** | Auto-reclose |
| **LOCKOUT** | Lockout / 86 |
| **UNKNOWN** | Leave unmapped |

Optionally bind an **element** (21, 51, 51N, 67N, 87L, …). Rising-edge logic respects configured normal state. After save → **Re-run analysis** so Sequence / Protection / Consistency update.

### DR workspace

Combined disturbance-record view for day-to-day DR review: waveforms, cursors, phasors, **R–X (faulted loop)**, harmonic bars, and **harmonics heatmap**. Upload **`.rio` / `.xrio`** with settings when you want trip-zone outlines on R–X.

### Waveforms

Interactive viewer with **real sample arrays** (from analysis cache / on-demand parse):

- Zoom / pan / cursors  
- Channel selection · analog/digital  
- Markers when available  
- Engineering units  

Inspect individual sample values — not smoothed-only curves.

### Sequence (timeline)

Chronological reconstruction (inception → pickup → trip → breaker → interruption → reclose/lockout when evidence exists). Digitals follow the **DR targets** map. Missing signals → **NOT AVAILABLE**. External SOE / event-report events may merge when parsers succeed.

### Electrical

RMS, phasors, sequences, power, impedance, harmonics, etc., each with method/quality. Missing → **NOT CALCULABLE**.

**Impedance / fault resistance table** — shows only the **faulted loop** for the classified fault (e.g. AG → `Z_AG`; ABG → `Z_AB`; ABC → `Z_AB` / `Z_BC` / `Z_CA`). Other phase/loop Z values may still be computed internally but are not listed as “the” fault impedance.

**R–X locus** — plotted only when distance / 21 context applies and a fault type is classified. Points are the faulted loop only. **Trip zones** appear when RIO/XRIO geometry or scalar zone reaches are available from settings (never invented).

**Harmonics** — fault-window harmonic bars plus a **time × order heatmap** (short-time DFT) for phase currents when calculable.

**Nominal voltage** — Overview shows kV from the event field; if empty, analysis fills it from settings text, VT ratio, or `…NNNkV…` in filename/station name when present.

### Fault / Location

Fault type / characteristics and distance / location views when inputs exist. Distance never invented — **NOT CALCULABLE** with reason when CT/VT/line/settings are incomplete.

### Protection

Per-element table: Enabled · Pickup · Trip · Expected · Timing · Consistency · Setting source · Evidence.

See also [§14 Protection physics and schemes](#14-protection-physics-and-schemes).

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

Uploaded settings are **auto-APPROVED** and the active group marked **VERIFIED** by default (see [§16](#16-settings-and-setting-hierarchy)). You can still confirm or re-approve manually if your site policy requires it.

**Mandatory rule:** `51 Enabled = FALSE` with pickup/trip observed → **INCONSISTENT** (typically HIGH). RCA remains **INCONCLUSIVE** regarding relay malfunction until active configuration is verified.

### RCA

Hypothesis board with status CONFIRMED / PROBABLE / POSSIBLE / UNLIKELY / INCONCLUSIVE, score, supporting / contradicting / missing evidence.

Scheme label (when detected) appears in the subtitle (e.g. stepped distance, feeder OC/EF, 87L+21).

**Cause enrichment (field / asset):** use the checkboxes on the RCA page (lightning evidence, vegetation field report, cable asset confirmed, …). Physical causes stay **INCONCLUSIVE** until these structured tokens are saved. After **Save cause evidence**, **Re-run analysis**.

**CONFIRMED** only when evidence requirements are met. Similarity and ML are supporting only. Zone / scheme mismatch → **UNLIKELY** for mismatched asset hypotheses.

**Transformer internal (87T / 87RGF):** CONFIRMED needs differential operate evidence **and** `through_fault_excluded`. The engine asserts through-fault exclusion when Id/Ir operate/restraint supports an internal fault, or (when winding phasors are missing) when 87T operated consistently without phase CT-sat / inrush indicators. Missing Id/Ir alone used to leave the hypothesis **PROBABLE** with “Missing evidence: through fault excluded.”

**Decision vs RCA:** A **CONFIRMED** primary hypothesis maps to **ANALYSIS_COMPLETE** unless **material** limitations remain (e.g. phase CT saturation POSSIBLE). Informational notes such as “Merged N external timeline events from SOE” do **not** downgrade the decision to WITH_WARNINGS. A **PROBABLE** primary still yields **ANALYSIS_COMPLETE_WITH_WARNINGS**.

### Evidence

```text
RCA → Hypothesis → Finding → Calculation → Source → Raw data / file
```

### Summary / Report / Review

Summary consolidates the event story. Report: see [§19 Reports](#19-reports-html-pdf-json).

| Review action | When to use |
|--------|-------------|
| **ACCEPT** | Agree with automated findings |
| **MODIFY** | Accept with documented corrections |
| **REJECT** | Reject automated conclusions |
| **INCONCLUSIVE** | Cannot close with available evidence |
| **REQUEST FIELD INVESTIGATION** | Need field verification |

Automated results are retained; overrides are audited separately.

---

## 14. Protection physics and schemes

### Element 51 / 51N / 51P — time overcurrent

When pickup current, time dial (TMS), curve type, and measured current are available, the engine computes expected operate time using IEC/IEEE inverse curves, for example:

- IEC Normal / Very / Extremely / Long-time Inverse  
- IEEE Moderately / Very / Extremely Inverse  

Formula family: `t = TDS × (A / (M^p − 1) + B)` for multiple `M > 1`.

Earth-fault (**51N**) and phase (**51P**) variants use the mapped residual / phase quantities. If inputs are missing → timing physics status **NOT_CALCULABLE**.

### Element 67 / 67N / 67P — directional overcurrent

Directional assessments use available voltage/current phasor relationships and settings. Missing polarizing quantity → **UNVERIFIABLE** / **NOT_CALCULABLE**, never invented direction.

### Element 21 — distance

When apparent impedance and zone reach settings exist, a deterministic **mho** (default) or simple **quad** reach check evaluates zone entry.

**R–X display:** uses the **faulted loop** impedance (phase–ground or phase–phase delta `(V1−V2)/(I1−I2)` as applicable). Zone outlines on the plot come from uploaded **RIO / XRIO** shapes or scalar Z1/Z2/Z3 reaches — never invented.

If impedance or reach is missing → **NOT_CALCULABLE** / fault distance not invented.

### Differential / BF (87L, 87T, 87B, 50BF)

Assessed when multi-end / winding / bus currents or BF timing evidence exist in the record or event meta. Insufficient inputs stay explicitly incomplete.

**87 operate/restraint:** when both-side currents exist, Id = |I1−I2|, Ir = (|I1|+|I2|)/2; trip expected if Id > Ip + k·Ir. The Protection tab can show an **Id/Ir** characteristic plot. Soft **CT saturation** cues use phase currents only (not residual IN alone).

### Scheme library (RCA context)

Deterministic scheme detection from operated/enabled elements and digital roles, for example:

- Stepped distance (21)  
- Line differential + distance (87L + 21)  
- POTT / communication-aided schemes (when channel evidence exists)  
- Feeder overcurrent / earth-fault  
- Transformer / bus / generator unit schemes  
- Breaker-failure cascade  

Scheme context influences RCA ranking; it does **not** invent trips or measurements.

---

## 15. Understanding status badges and quality labels

### Decision states

| State | Typical meaning |
|-------|-----------------|
| **ANALYSIS_COMPLETE** | Primary RCA **CONFIRMED** and no material analysis warnings |
| **ANALYSIS_COMPLETE_WITH_WARNINGS** | Primary is **PROBABLE**, or CONFIRMED with material warnings (e.g. phase CT sat) |
| **ENGINEER_REVIEW_REQUIRED** | Primary POSSIBLE / INCONCLUSIVE / UNLIKELY |
| **INCONCLUSIVE** | Forced by critical setting policy or no usable primary |
| **DATA_INSUFFICIENT** / **UNSUPPORTED_FORMAT** | Record/format blocks analysis |

Informational limitations (unused loops “NOT AVAILABLE”, SOE timeline merge notes, distance NOT APPLICABLE for feeder OC schemes) are listed for transparency but do **not** by themselves keep a CONFIRMED case in WITH_WARNINGS.

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

## 16. Settings and setting hierarchy

Navigate settings from the event workspace (uploaded packages) and consistency panels. Version / group priority (highest first):

1. Event-specific active setting  
2. Active setting group  
3. Approved relay base setting  
4. Relay configuration  
5. Historical setting  
6. Engineering design setting  

The UI shows which source was used. The system **never silently picks** a group without displaying it.

### Auto-approve uploaded settings (default)

When a settings file (JSON / text / vendor extract / `.set` / `.xrio` / `.rio`, …) is loaded with the event, the platform treats it as:

- **Approval:** APPROVED  
- **Active group:** VERIFIED  

unless the package explicitly marks `DRAFT` / `REJECTED` / `PENDING` / `PENDING_REVIEW`.

Environment override: set `AUTO_APPROVE_UPLOADED_SETTINGS=false` to require manual Approve / Confirm active group again.

After changing this policy or uploading a new settings file, **Re-run analysis** so Consistency / Protection use the updated approval flags.

### Nominal system voltage from settings

If Overview shows **UNKNOWN kV**, analysis still tries to fill `nominal_voltage_kv` from:

1. Explicit JSON keys / asset fields  
2. Settings text lines such as `Nominal System Voltage : 132 kV`  
3. VT ratio primary (e.g. `132000/110` → 132 kV)  
4. Filename or station name tokens such as `132kV`

Never invents a voltage without one of these evidences.

---

## 17. Databases (auth vs plant/events)

Local / portable SQLite layout (under `backend\`):

| File | Contents |
|------|----------|
| **`protection_rca_auth.db`** | Users, passwords, auth sessions |
| **`protection_rca_local.db`** | Plant hierarchy, events, analysis artefacts metadata |

### Why two databases?

Clearing plant/event data for a clean engineering trial **does not** wipe logins. You keep `admin` / other accounts while resetting events.

### How to clear data safely

**Events and plant only (keep logins):**

1. Stop `ProtectionRCA.exe`
2. Delete `backend\protection_rca_local.db` (and `-wal` / `-shm` if present)
3. Optionally delete `backend\storage\` event/report blobs
4. Optionally clear browser localStorage key `protection_rca_recent_events_v1` (Continue button)
5. Restart the exe — plant tree and events are empty; log in as before

**Full wipe including users:**

Also delete `backend\protection_rca_auth.db`. Next start recreates bootstrap **`admin` / `admin123`** (or your `BOOTSTRAP_ADMIN_*` values).

Docker / PostgreSQL deployments use the configured application database; auth separation above applies to the local SQLite dual-DB mode.

---

## 18. Rules, models, and historical similarity

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

## 19. Reports (HTML, PDF, JSON)

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

## 20. Users, SSO, and audit

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

## 21. Supported file types and COMTRADE matrix

| Extension | Typical content |
|-----------|-----------------|
| `.cfg` / `.dat` | COMTRADE configuration + data |
| `.cff` | Combined COMTRADE file |
| `.hdr` / `.inf` | Header / information |
| `.csv` / `.txt` / `.log` | SOE / SER / event reports (when parsers exist) |
| `.xml` / `.json` / `.set` / `.xrio` / `.rio` | Settings / configuration / trip-zone exports |
| `.rdb` | SEL settings database (SET_ALL extract when present) |
| `.cev` | SEL compressed event — converted to CFG+DAT when convertible |
| `.eve` | Relay event report text (parsed when recognized) |
| `.dz5` / `.dex5` / `.d5z` / `.pcmi` / `.pcmp` | DIGSI / PCM600-style packages (ZIP-expand when possible) |
| `.pdf` | Supporting attachment (reports, drawings, notes) — stored, not parsed as COMTRADE |
| `.zip` | Package archive — **auto-extracted**; allowed members processed further; ZIP kept as PACKAGE |

Detection prefers **file contents**, not extension alone. Proprietary non-extractable blobs are reported honestly (**NOT CALCULABLE** / unsupported) rather than silently invented.

Supported / regression-covered COMTRADE families (see `docs/COMTRADE_SUPPORT.md` for partial notes):

| Variant | Notes |
|---------|-------|
| IEEE C37.111-1999 / 2013 | Primary |
| IEEE C37.111-1991 | Partial support — fixtures included |
| IEC 60255-24:2001 / 2013 | Via aliases / detectors |
| ASCII · BINARY · BINARY32 · FLOAT32 | Parsers + golden fixtures |
| CFF | Detect / unpack path + fixture |

---

## 22. Sample / test / golden data

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

Create a plant path ending in an IED, upload test files on that IED, run analysis, and explore each tab.

---

## 23. Engineering language used in reports

Controlled templates only. Examples:

- OBSERVED: trip digital was present  
- CALCULATED: apparent impedance entered Zone 1 reach  
- INFERRED: operation consistent with configured reach  
- HYPOTHESIS: internal feeder fault is probable  

Never treat fluent wording as stronger than status badges.

---

## 24. Frequently asked questions

**Q: Where is Create event / Upload in the menu?**  
A: Removed on purpose. Go to **Plant**, build Substation → Voltage → Bay → Feeder → IED, then **Open** the IED and upload there.

**Q: How do I create my first event?**  
A: Plant → **+ Substation** → **+ Voltage** → **+ Bay** → **+ Feeder** → **+ IED** → **Open** → drop CFG/DAT (or ZIP). Then open the new event and run analysis.

**Q: Default login?**  
A: `admin` / `admin123` on a fresh auth database. Change it for production.

**Q: I deleted the local DB and cannot log in**  
A: You deleted `protection_rca_auth.db` as well. Restart the app to recreate bootstrap admin, or keep auth DB and only delete `protection_rca_local.db` when clearing events.

**Q: Why are Location / Relay / Fault columns empty?**  
A: Upload under an IED so plant labels attach; complete analysis for fault / protection columns. Protection shows operated elements (e.g. 87T, 51N) when available.

**Q: Search on All events does nothing useful**  
A: Type any fragment of ID, station, bay, relay, fault, or protection code (e.g. `IED-4`, `Bay 1`, `51N`). Use From/To for dates. Click **Clear filters** to reset (also clears Dashboard queue filters).

**Q: Why is RCA INCONCLUSIVE?**  
A: Consistency findings (e.g. disabled 51 operating), or missing evidence for CONFIRMED. Uploaded settings are auto-APPROVED by default — INCONCLUSIVE is no longer forced solely by “NOT VERIFIED” upload flags.

**Q: Why does Decision say WITH_WARNINGS when RCA is CONFIRMED?**  
A: Older builds downgraded on any limitation text. Current behaviour: CONFIRMED → ANALYSIS_COMPLETE unless **material** warnings remain. Informational notes (SOE merge, unused loops) do not force WITH_WARNINGS. Re-run analysis on older events.

**Q: Why does the impedance table show only one Z row?**  
A: By design — only the **faulted loop** for the classified fault (AG→ZAG, ABG→ZAB, …). Other loops are not listed as the event fault impedance.

**Q: Why is Nominal UNKNOWN kV?**  
A: The event field was empty and no voltage evidence was found in settings/VT/filename/station. After uploading settings that state nominal kV (or a VT ratio), **Re-run analysis**.

**Q: Do I still need to Approve settings?**  
A: Not by default — uploads are auto-APPROVED / active group VERIFIED. Set `AUTO_APPROVE_UPLOADED_SETTINGS=false` to restore manual approval.

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
A: Yes — on the IED workspace (or event Files tab). The ZIP is auto-extracted; COMTRADE/settings/SOE/PDF/vendor members are stored and used. The original ZIP remains as evidence.

**Q: Can I upload SEL `.rdb` / `.cev` or DIGSI / PCM600 packages?**  
A: Yes where extractable. `.rdb` → settings when SET_ALL is present; `.cev` → CFG+DAT when convertible; DIGSI/PCM600 packages expand nested COMTRADE/settings when ZIP-like. Opaque proprietary blobs stay unsupported — export CFG/DAT from the vendor tool if needed.

**Q: Why is analysis FAILED but older results still visible?**  
A: Background analysis failed on the latest job. Hover FAILED / open Details for the error, fix Channel map / DR targets / files, then **Re-run analysis**. Prior completed artefacts may remain until overwritten.

**Q: Pipeline still says “Queued (background)” after FAILED?**  
A: That was the last progress message before the job crashed. Use the FAILED badge / error text and re-run after fixing inputs. Restart the app if you just updated the backend.

**Q: Lightning / vegetation / cable stay INCONCLUSIVE**  
A: Open Protect → **RCA**, tick the matching **cause enrichment** evidence, save, then **Re-run analysis**. Waveforms alone do not invent physical root causes.

**Q: Pickup / trip times look wrong**  
A: Open Setup → **DR targets**, map the correct digitals (and element), save, re-run. Rising-edge logic depends on the mapped role and normal state.

**Q: Electrical / distance looks wrong after auto-detect**  
A: Open Setup → **Channel map**, correct Ia/Ib/Ic/Va… roles, save, re-run.

**Q: Can I delete an event?**  
A: Yes — All events **Delete**, or event header **Delete event** (ANALYST+). Confirm first. Continue memory for that ID is cleared.

**Q: KPI click does nothing useful**  
A: It opens All events with a queue filter. Use **Clear filters** to reset.

**Q: Continue button still shows a deleted event**  
A: Refresh the page after delete; the app prunes recent-event memory when the event is gone or the events DB is empty. You can also clear browser localStorage key `protection_rca_recent_events_v1`.

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

## 25. Troubleshooting

| Symptom | What to check |
|---------|----------------|
| Exe says backend/frontend not found | Run `ProtectionRCA.exe` from inside `protection-rca` or `portable-share` |
| UI blank / API errors | http://127.0.0.1:8001/health |
| Port in use | Portable UI+API: **8001**; Vite UI: **5173** |
| Colleague cannot open LAN URL | Same Wi‑Fi/LAN; use host IP not 127.0.0.1; allow Windows Firewall private network for port **8001** |
| Exe rebuild “Access denied” / false “EXE OK” | Close all `ProtectionRCA.exe` windows (Task Manager if needed). Prefer `scripts\build-all-latest.bat` — it kills locked processes and fails the build if PyInstaller cannot write the EXE |
| Cannot log in after DB clear | Ensure `protection_rca_auth.db` exists or restart for bootstrap `admin` / `admin123` |
| No Create event menu | Use **Plant → IED → upload** |
| Search finds nothing unexpected | Clear filters; confirm spelling; protection codes like `87T` are searchable |
| Date filter misses events | Leave To at 00:00 to include whole day; times are local |
| Settings still NOT VERIFIED / Decision WITH_WARNINGS on old events | **Re-run analysis** after upgrading — approval and decision gating apply on the new run |
| Upload rejected | Extension, size limit, or role; must upload from IED workspace or event Files |
| COMTRADE INVALID | Fix source export; do not force confident RCA |
| Analysis FAILED / “background analysis failed” | Hover FAILED for `error_message`; fix Channel map / DR targets / files; **Re-run**; restart exe after backend updates |
| Stuck “Queued (background)” with FAILED | Latest job never advanced — re-run after fix; check API logs if it fails again immediately |
| Waveforms empty | Analysis/parse not run or validation failed |
| Wrong pickup/trip sequence | Setup → **DR targets** → save → re-run |
| Wrong phasors / distance | Setup → **Channel map** → save → re-run |
| Consistency empty | Analysis not run or no digital/setting inputs |
| Vendor `.rdb` / `.cev` / DIGSI unused | Confirm extract succeeded on Files tab; else export CFG/DAT + settings text from vendor tool |
| PDF download fails | Ensure `reportlab` installed in backend env |
| Cannot review | Role below PROTECTION_ENGINEER / APPROVER |

API docs: http://127.0.0.1:8001/docs

---

## 26. Where to find more documentation

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

## 27. Quick reference card

```text
START     → Double-click ProtectionRCA.exe (portable: :8001 · dev: :5173)
STOP      → Close launcher control window
SHARE     → scripts\build-portable-share.bat → zip portable-share\
LAN       → Others open http://<host-IP>:8001/ (Firewall allow)
LOGIN     → admin / admin123 (bootstrap) or SSO if configured
PLANT     → Substation → Voltage → Bay → Feeder → IED → Open
UPLOAD    → On IED workspace (CFG/DAT/CFF/ZIP/vendor) — not a global Upload menu
MAP       → Setup → Channel map + DR targets → save
ANALYSE   → Start / Re-run analysis (background) → watch status bar
VERIFY    → Waveforms → Sequence → Consistency → RCA → Evidence
CAUSE     → RCA cause enrichment (field evidence) → re-run
FILTER    → All events: Search + From/To + Clear filters
REPORT    → Download HTML or PDF
CLOSE-OUT → Review (ACCEPT / MODIFY / REJECT / …)
DELETE    → All events → Delete (ANALYST+)
DBS       → auth.db = users · local.db = plant/events
REMEMBER  → No invented data · No OT control · No generative AI
```

---

*End of User Guide — Protection RCA Platform (document version 0.6.0)*
