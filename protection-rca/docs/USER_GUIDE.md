# Protection RCA — User Guide

**Audience:** Protection engineers, analysts, approvers, and administrators  
**Product:** Protection Disturbance Record (DR) / COMTRADE analysis and Root Cause Analysis (RCA) platform  
**Document version:** 0.5.0  
**Application:** Protection RCA web application (React + FastAPI)

This guide explains how to launch the application, create and analyse disturbance events, interpret results, generate reports, and complete engineer review. It reflects the **current implemented behaviour** of the platform.

---

## Document revision — what is covered in this edition

This edition (**0.5.0**) documents platform upgrades since 0.4.0, including:

| Area | What changed |
|------|----------------|
| **R–X locus** | Shows the **faulted loop only** (e.g. AG → ZAG; ABG → ZAB). Not all phase self-impedances for every fault |
| **Trip zones on R–X** | Real **RIO / XRIO** (and scalar `21` reach) zone geometry — mho circles and polygons — when settings files provide them |
| **Impedance table** | Electrical → Impedance lists **faulted-loop** rows only (title shows e.g. `AG loop`) |
| **Harmonics heatmap** | Time × harmonic-order heatmap (short-time DFT) on Electrical and DR workspace, alongside harmonic bars |
| **Id / Ir (87)** | Differential operate/restraint plot and physics when both-side / winding currents exist |
| **87T through-fault** | `through_fault_excluded` for CONFIRMED transformer internal RCA when Id/Ir supports internal operate, or soft path when Id/Ir unavailable and phase CT-sat / inrush are not indicated |
| **CT saturation detector** | Soft indicators use **phase currents (IA/IB/IC) only** — residual/IN high H2 during earth faults is not treated as phase CT sat |
| **Decision badges** | **CONFIRMED** primary → `ANALYSIS_COMPLETE` unless **material** warnings (e.g. phase CT sat). Informational notes (SOE merge, unused loops) do **not** force WITH_WARNINGS. **PROBABLE** still → WITH_WARNINGS |
| **Nominal voltage** | Auto-filled from settings text (`Nominal System Voltage`), VT ratio (e.g. `132000/110`), filename / station `…132kV…` when the event field was empty |
| **Settings auto-approve** | Uploaded settings files are treated as **APPROVED** and active group **VERIFIED** automatically (`AUTO_APPROVE_UPLOADED_SETTINGS`, default on). Explicit DRAFT/REJECTED/PENDING packages are left alone |
| **`.rio` upload** | Classic RIO trip-zone files accepted with settings / XRIO |
| **Portable build** | `build-all-latest.bat` stops a running `ProtectionRCA.exe` before rebuild and fails if PyInstaller errors (avoids false “EXE OK” when Access denied) |

Earlier **0.4.0** coverage (still valid):

| Area | What changed |
|------|----------------|
| **Portable package** | `scripts\build-portable-share.bat` builds a shareable folder (exe + backend venv + built UI) — no Python/Node install on the other PC |
| **LAN access** | Launcher binds API/UI for network use; control window shows LAN URLs (e.g. `http://192.168.x.x:8001/`) |
| **Portable run mode** | When `frontend\dist` exists, exe serves UI+API on **port 8001** (single process); otherwise Vite UI on **5173** |
| **Dashboard** | Clickable KPI tiles, 7/30/90-day trend, data-quality donut, Attention Required, richer Recent Events, empty-state workflow |
| **Navigation** | Grouped sidebar: Operations · Plant · Engineering · Administration · Help |
| **Create Event wizard** | Multi-step page at `/events/new`: Info → Upload → Detect → Validate → Analyse |
| **Event workspace** | Tab groups **Setup · Analyse · Protect · Conclude**; pipeline lamps (COMTRADE / DATA / SETTINGS / PROTECTION / CONSISTENCY / RCA / REPORT) |
| **Channel map** | Setup → **Channel map** — assign analog roles (Ia/Ib/Ic/In, Va/Vb/Vc, …) before trusting electrical / distance results |
| **DR targets** | Setup → **DR targets** — map digital channels to Pickup / Trip / 52A / 52B / Reclose / Lockout (+ element) for timeline and protection |
| **Vendor packages** | SEL `.rdb` / `.cev`, DIGSI/PCM600 packages (`.dz5` / `.dex5` / `.d5z` / `.pcmi` / `.pcmp`), `.set` / `.xrio` / `.eve` / `.log` where extractable |
| **Background analysis** | Analyse returns immediately; job runs in the background. Failures show the real error (hover FAILED badge / Details). Re-run after maps or settings change |
| **Scheme library** | Scheme-aware RCA context (stepped 21, 87L+21, POTT, feeder OC/EF, transformer/bus/gen unit, BF cascade) from operated/enabled elements |
| **Cause enrichment** | Protect → **RCA** — engineer checkboxes for lightning / vegetation / cable (etc.); physical causes stay INCONCLUSIVE until structured evidence is saved, then **re-run analysis** |
| **Protection breadth** | Inverse-time **51 / 51N / 51P**; directional **67 / 67N / 67P**; differential **87L / 87T / 87B**; **50BF**; distance **21** |
| **Overview** | What happened · Why · Which setting · What is uncertain · What should I verify |
| **Waveforms** | Real sample streaming from parsed COMTRADE (cached samples, not metadata-only) |
| **RCA hypotheses** | Zone/scheme-aware ranking; lightning/vegetation/cable only when field/asset evidence tokens exist |
| **Reports** | Deterministic HTML + **PDF download** (ReportLab); JSON machine-readable companion |
| **Upload attachments** | **`.pdf`** and **`.zip`** allowed; ZIP packages **auto-extract**; vendor binaries expanded when supported |
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
13. [Protection physics and schemes](#13-protection-physics-and-schemes)
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

- Create disturbance events and upload COMTRADE / ZIP / vendor packages / PDF attachments
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
2. Upload disturbance package (CFG+DAT / CFF / ZIP / vendor package)
3. Confirm COMTRADE detection / validation
4. Setup → Channel map + DR targets (correct if auto-infer looks wrong)
5. Start / Re-run analysis (runs in background — watch status bar)
6. Inspect DR workspace / Waveforms / Sequence (timeline)
7. Review Electrical + Fault + Location + Protection
8. Study Consistency (setting source!)
9. Study RCA + Evidence (+ cause enrichment if field evidence exists)
10. Download Report (HTML / PDF)
11. Complete Engineer Review
```

Do **not** skip Consistency when RCA looks “confident.” Consistency findings often explain why RCA must stay inconclusive.

After changing **Channel map**, **DR targets**, settings, or **cause evidence**, always **Re-run analysis** so timeline, protection, consistency, and RCA refresh.

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
`.cfg .dat .cff .hdr .inf .csv .txt .xml .json .pdf .zip`  
plus vendor / settings packages:  
`.set .rdb .xrio .rio .eve .cev .log .dz5 .dex5 .d5z .pcmi .pcmp`.

**ZIP packages:** uploading a `.zip` **auto-extracts** the archive. Each allowed member (COMTRADE, settings, SOE, PDF, vendor extractables, etc.) is stored as its own immutable event file and used for detection, validation, and analysis. The original ZIP is kept as a **PACKAGE** attachment for evidence. Nested ZIPs are expanded (limited depth). Unsupported members are skipped (recorded in metadata). Path-traversal / zip-bomb guards apply.

**Vendor notes (honest):**

| Format | Behaviour |
|--------|-----------|
| SEL `.rdb` | OLE container — SET_ALL text extracted when present → settings ingest |
| SEL `.cev` | Converted to CFG+DAT for waveform / timeline use when convertible |
| DIGSI / PCM600 `.dz5` / `.dex5` / `.d5z` / `.pcmi` / `.pcmp` | Treated as ZIP-like packages when they contain nested COMTRADE / settings / CEV; proprietary non-ZIP blobs stay **NOT CALCULABLE** with export guidance |
| `.set` / `.xrio` / `.rio` / `.eve` / `.log` / SOE CSV | Parsed when structure is recognized; RIO/XRIO supply distance trip-zone geometry for R–X when present |

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
- Or upload a **ZIP** / vendor package containing CFG/DAT/CFF (+ settings / SOE / PDF)
- Include settings exports / event reports / PDF attachments when available
- After upload, confirm **Channel map** and **DR targets** before trusting protection timing
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

1. After upload/validation (and preferably after Channel map / DR targets), start analysis from the wizard Step 5 or the event workspace (**Start analysis** / **Re-run analysis**)
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

## 12. Event analysis workspace (detailed)

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

See also [§13 Protection physics and schemes](#13-protection-physics-and-schemes).

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

Uploaded settings are **auto-APPROVED** and the active group marked **VERIFIED** by default (see [§15](#15-settings-and-setting-hierarchy)). You can still confirm or re-approve manually if your site policy requires it.

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

Summary consolidates the event story. Report: see [§18 Reports](#18-reports-html-pdf-json).

| Review action | When to use |
|--------|-------------|
| **ACCEPT** | Agree with automated findings |
| **MODIFY** | Accept with documented corrections |
| **REJECT** | Reject automated conclusions |
| **INCONCLUSIVE** | Cannot close with available evidence |
| **REQUEST FIELD INVESTIGATION** | Need field verification |

Automated results are retained; overrides are audited separately.

---

## 13. Protection physics and schemes

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

## 14. Understanding status badges and quality labels

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
A: Yes. The ZIP is auto-extracted; COMTRADE/settings/SOE/PDF/vendor members are stored and used in detect → validate → analysis. The original ZIP remains as evidence.

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
| Exe rebuild “Access denied” / false “EXE OK” | Close all `ProtectionRCA.exe` windows (Task Manager if needed). Prefer `scripts\build-all-latest.bat` — it kills locked processes and fails the build if PyInstaller cannot write the EXE |
| Settings still NOT VERIFIED / Decision WITH_WARNINGS on old events | **Re-run analysis** after upgrading — approval and decision gating apply on the new run |
| Upload rejected | Extension, size limit, or role |
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
NEW WORK  → Create event wizard → upload CFG/DAT/CFF/ZIP/vendor package
MAP       → Setup → Channel map + DR targets → save
ANALYSE   → Start / Re-run analysis (background) → watch status bar
VERIFY    → Waveforms → Sequence → Consistency → RCA → Evidence
CAUSE     → RCA cause enrichment (field evidence) → re-run
REPORT    → Download HTML or PDF
CLOSE-OUT → Review (ACCEPT / MODIFY / REJECT / …)
DELETE    → Events Actions → Delete (ANALYST+)
REMEMBER  → No invented data · No OT control · No generative AI
```

---

*End of User Guide — Protection RCA Platform (document version 0.5.0)*
