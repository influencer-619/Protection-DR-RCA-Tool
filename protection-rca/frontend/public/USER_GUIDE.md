# Protection RCA — User Guide

**Audience:** Protection engineers, analysts, approvers, and administrators  
**Product:** Protection Disturbance Record (DR) / COMTRADE analysis and Root Cause Analysis (RCA) platform  
**Document version:** 0.7.0  
**Application:** Protection RCA web application (React + FastAPI)

This guide explains how to launch the application (including the portable, no-install build), build the plant hierarchy, bring disturbance records in — either by **fetching them directly from the relay over IEC 61850** or by **manual upload** — analyse each event, interpret the results, generate reports, and complete engineer review. It reflects the **current implemented behaviour** of the platform.

---

## Document revision — what is covered in this edition

This edition (**0.7.0**) adds IEC 61850 acquisition, readable event numbers, the refreshed user interface, and a truly self-contained portable build:

| Area | What changed |
|------|----------------|
| **Fetch from IED (IEC 61850)** | New **Fetch from IED** mode on every IED workspace. Connects read-only over MMS (port 102), identifies the relay from its nameplate, lists disturbance records on the relay, and pulls COMTRADE + settings + protection events + optional SCL into a new event. See [§10](#10-fetching-records-from-the-relay-iec-61850) |
| **Vendor profiles** | Auto-detect plus ABB/Hitachi, Siemens, GE Vernova, Schneider, SEL, NR, Toshiba, ZIV and a generic profile — each knows where that vendor stores records |
| **Automatic fetch** | Per-IED **Auto-fetch new records** switch. The server polls the relay on a schedule (1 min … 4 h), creates one event per new record, and can start analysis automatically — even when nobody has the page open. See [§11](#11-automatic-fetch-auto-fetch) |
| **Event numbers** | New events get readable IDs **`EVT-YYYY-NNNNN`** (e.g. `EVT-2026-00042`). Older random (UUID) IDs are renumbered once at startup; the old ID is kept for traceability. See [§12](#12-event-numbers) |
| **Application shell** | Collapsible left sidebar (remembered per browser), top bar with breadcrumb, theme toggle, user chip and sign-out |
| **Plant page** | Level stat cards (1–5), inline “New … under …” add bar, tree filter, **Expand all / Collapse all**, event counts per IED |
| **IED workspace** | Header with full plant path and tag / kV / IP chips, stats (Events · In review · Last event), **Fetch from IED / Manual upload** switch, drag-and-drop zone with file chips, event list for the relay |
| **Event workspace** | New header band (breadcrumb, title, date, badges, Share / Start / Re-run / Delete), clickable pipeline lamps, one sticky tab bar, progress panel only while a job runs |
| **Reports & summary** | Report preview and Summary sheet always render as a light “paper” page (readable in dark theme), without affecting the rest of the app |
| **Audit** | Shows **usernames** instead of IDs (“system” for automatic actions), coloured action chips, text filter, entry count. New actions: `IEC61850_FETCH`, `IEC61850_AUTO_FETCH` |
| **Portable build** | `portable-share\python\` now contains a **complete Python runtime** — the other PC needs **no Python, no Node, no install**. The launcher logs API start-up to `backend\logs\api-launch.log` and shows the log tail if the API fails to start |

Still valid from **0.6.0** (plant-first workflow):

| Area | Summary |
|------|---------|
| **Plant-first workflow** | No global Create event / Upload menus. Build **Substation → Voltage level → Bay → Feeder → IED**, then work on the IED |
| **All events** | Global list with live **Search** and **From / To** date filters, “X of Y events”, **Clear filters** |
| **Protection column** | Operated elements (e.g. **51N, 87T, 21**) plus fault type where known |
| **Dashboard** | Work inbox, Operations + Quality KPI rows, trend chart, Attention queue, DQ donut, Recent events |
| **Dual SQLite DBs** | Users in `protection_rca_auth.db`; plant + events in `protection_rca_local.db` |
| **Bootstrap admin** | Fresh install: **`admin` / `admin123`** (change in production) |

Still valid from **0.5.0** (engineering analysis): faulted-loop R–X / impedance, harmonics heatmap, 87 Id–Ir, through-fault exclusion, decision badges, settings auto-approve, Channel map, DR targets, background analysis, scheme library, cause enrichment, HTML/PDF/JSON reports, no generative AI, no OT control.

---

## Table of contents

1. [What this tool is (and is not)](#1-what-this-tool-is-and-is-not)
2. [Starting and stopping the application](#2-starting-and-stopping-the-application)
3. [Signing in (local and SSO)](#3-signing-in-local-and-sso)
4. [Roles and permissions](#4-roles-and-permissions)
5. [Application layout and navigation](#5-application-layout-and-navigation)
6. [Dashboard (operations console)](#6-dashboard-operations-console)
7. [Recommended workflow (end-to-end)](#7-recommended-workflow-end-to-end)
8. [Plant hierarchy](#8-plant-hierarchy)
9. [IED workspace](#9-ied-workspace)
10. [Fetching records from the relay (IEC 61850)](#10-fetching-records-from-the-relay-iec-61850)
11. [Automatic fetch (auto-fetch)](#11-automatic-fetch-auto-fetch)
12. [Event numbers](#12-event-numbers)
13. [All events (list and filters)](#13-all-events-list-and-filters)
14. [Uploading files manually](#14-uploading-files-manually)
15. [COMTRADE detection and validation](#15-comtrade-detection-and-validation)
16. [Running analysis](#16-running-analysis)
17. [Event analysis workspace (detailed)](#17-event-analysis-workspace-detailed)
18. [Protection physics and schemes](#18-protection-physics-and-schemes)
19. [Understanding status badges and quality labels](#19-understanding-status-badges-and-quality-labels)
20. [Settings and setting hierarchy](#20-settings-and-setting-hierarchy)
21. [Databases (auth vs plant/events)](#21-databases-auth-vs-plantevents)
22. [Rules, models, and historical similarity](#22-rules-models-and-historical-similarity)
23. [Reports (HTML, PDF, JSON)](#23-reports-html-pdf-json)
24. [Users, SSO, and audit](#24-users-sso-and-audit)
25. [Supported file types and COMTRADE matrix](#25-supported-file-types-and-comtrade-matrix)
26. [Sample / test / golden data](#26-sample--test--golden-data)
27. [Engineering language used in reports](#27-engineering-language-used-in-reports)
28. [Frequently asked questions](#28-frequently-asked-questions)
29. [Troubleshooting](#29-troubleshooting)
30. [Where to find more documentation](#30-where-to-find-more-documentation)
31. [Quick reference card](#31-quick-reference-card)

---

## 1. What this tool is (and is not)

### What it is

An **engineering decision-support web application** that helps you:

- Build a **plant hierarchy** (Substation → Voltage → Bay → Feeder → IED)
- **Fetch disturbance records, settings and protection events directly from the relay** over IEC 61850 (read-only), manually or automatically on a schedule
- Upload COMTRADE / ZIP / vendor packages / PDF **on each IED** when the relay is not reachable
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
| Relay / breaker control | **Read-only.** IEC 61850 access only *reads* files and data attributes. No control commands, no setting writes, no file deletion on the IED |
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

1. Open the project folder `protection-rca` **or** the portable folder `portable-share`
2. Double-click **`ProtectionRCA.exe`**
3. Wait until the browser opens:
   - **Portable mode** (when `frontend\dist\index.html` exists): `http://127.0.0.1:8001/`
   - **Dev mode** (no built UI yet): `http://127.0.0.1:5173/`
4. A small window appears: **“Protection RCA is running”** — it also lists **LAN URLs** for other PCs

**To stop everything:** close that window (or click **Stop & Close**).  
This shuts down the API and UI processes started by the launcher.

> Keep the control window open while you work. Closing a browser tab alone does **not** stop the services. IEC 61850 auto-fetch also runs only while the application is running.

#### What the launcher does on start

1. Finds a Python runtime — in the portable build it always uses the **bundled** `python\python.exe`
2. Starts the API (FastAPI / uvicorn) on port **8001** and writes its console output to **`backend\logs\api-launch.log`**
3. Waits up to **90 seconds** for `http://127.0.0.1:8001/health` to answer (the first launch on a new PC is slower because antivirus scans the files)
4. Opens the browser and shows the control window

If the API does not come up, the launcher shows **“API did not start on port 8001”** together with the **last lines of `api-launch.log`** — that text tells you the real cause (missing file, port busy, database locked, …). See [§29 Troubleshooting](#29-troubleshooting).

### Option B — Share with another person (no install on their PC)

Do **not** send only the `.exe`. Build the complete portable folder on your machine, then zip and send it.

```bat
cd protection-rca
scripts\build-portable-share.bat
```

That creates / refreshes `protection-rca\portable-share\` containing:

| Item | Purpose |
|------|---------|
| `ProtectionRCA.exe` | Launcher |
| `python\` | **Complete standalone Python runtime** with all backend packages (FastAPI, SQLAlchemy, NumPy, ReportLab, IEC 61850 client, …). The other PC needs **no Python installation** |
| `backend\` | API source code, SQLite databases, storage |
| `frontend\dist\` | Built web UI — no Node/npm install |
| `rules\` | RCA / protection rule catalogs |
| `templates\` | Report template and controlled sentence library (needed for HTML/PDF reports) |
| `scripts\` | Launcher script used by the exe |
| `HOW_TO_RUN.txt` | Short start / LAN instructions |

What the build script checks at the end:

- `portable-share\python\python.exe` exists
- The bundled Python can `import uvicorn, fastapi, sqlalchemy, numpy`

If either check fails the build stops with an error instead of producing a folder that will not start on another PC.

The build **replaces only** `backend`, `frontend`, `rules`, `scripts`, `python` and the exe inside `portable-share`. Any other folders you keep there (for example sample event folders such as `132kV_Feeder_Fault_Events\`) are **preserved**.

**On the other laptop:**

1. Unzip the folder anywhere (keep the internal structure — `python\`, `backend\`, `frontend\` must stay next to the exe).
2. Double-click `ProtectionRCA.exe`.
3. Browser opens `http://127.0.0.1:8001/`.
4. Close the control window to stop.

Requirements: Windows 10/11 64-bit. Nothing else. Antivirus may scan the first launch — allow the app if prompted.

> Always rebuild `portable-share` (and re-zip it) after updating the application, otherwise colleagues keep running the old version.

### Option C — Network access while you run it (LAN)

Use this when **your laptop hosts** the app and colleagues open it from their browsers on the **same Wi-Fi / office LAN**.

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
- For IEC 61850 fetch, it is the **host PC** (the one running the exe) that connects to the relays, so the host must be able to reach the relay network on TCP port 102.

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

Launcher environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `PROTECTION_RCA_PORT` | `8001` | API (and portable UI) port |
| `PROTECTION_RCA_HOST` | `0.0.0.0` | API bind address (all interfaces → LAN access) |
| `PROTECTION_RCA_UI_PORT` | `5173` | Vite dev UI port |
| `PROTECTION_RCA_DEV` | — | `1` forces dev (Vite) UI |
| `PROTECTION_RCA_PORTABLE` | — | `1` forces portable mode |

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

Database migrations: Alembic revision `0001_initial_schema` creates the application schema. Local scripted / portable runs use **two SQLite files** (see [§21](#21-databases-auth-vs-plantevents)); Compose uses PostgreSQL for application data.

See `README.md` and `docs/DEPLOYMENT.md`.

### Folder layout reminder

`ProtectionRCA.exe` must stay **inside** the `protection-rca` folder **or** the `portable-share` folder so it can find:

- `python\` (portable) or `backend\.venv` (developer machine)
- `backend\`
- `frontend\` (portable needs `frontend\dist\`; dev may also use Node via `.tools\node\` or a system install)
- `rules\` (analysis catalogs)

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

Click the **sign-out icon** (arrow out of a door) at the right end of the top bar.

---

## 4. Roles and permissions

| Role | Typical use |
|------|-------------|
| **VIEWER** | Read dashboards, events, reports, IEC 61850 connection status |
| **ANALYST** | Build plant, upload on IED, **test / browse / fetch from IED**, switch auto-fetch on/off, **Check now**, start analysis, delete events |
| **PROTECTION_ENGINEER** | Settings, consistency interpretation, review actions |
| **APPROVER** | Approvals, audit access |
| **ADMIN** | Users, rules/models administration |

Higher roles include the rights of lower ones. Authorization is enforced on the server. If a button fails with “forbidden”, your role is insufficient.

---

## 5. Application layout and navigation

### Sidebar (left)

| Group | Menu | Purpose |
|-------|------|---------|
| — | **Plant** | Build and browse the hierarchy; open an IED to fetch or upload records |
| **Analysis** | **Dashboard** | Work inbox, KPIs, trend, attention queue, recent events |
| **Analysis** | **All events** | Global list with search + date filters; Compare; Continue last event |
| **Administration** | **Users** | Account administration |
| **Administration** | **Audit** | Audit trail |
| Footer | **Help & guide** | In-app help and this user guide |

**Collapse / expand:** the chevron button at the bottom of the sidebar shrinks it to an icon rail (hover an icon to see its name). The choice is remembered in your browser.

> **Removed from the sidebar (by design):** standalone **Create event** and **Upload** pages. Records always come in through **Plant → IED** (fetch or upload). Old `/events/new` and upload-only routes redirect to **Plant**.

### Top bar

| Element | Purpose |
|---------|---------|
| Breadcrumb | `Protection RCA › <page>` (Plant hierarchy, IED workspace, Dashboard, All events, Event analysis, Compare events, Users, Audit trail, Help & guide) |
| **COMTRADE RCA** chip | Environment indicator |
| Theme icon | Switch **light / dark** theme (remembered per browser) |
| User chip | Your initials, name and role |
| Sign-out icon | Log out |

### Common UI conventions

- **Pills / badges** are colour-coded by meaning (green = good/complete, amber = warning/review, red = failed/high, grey = not available). Hover a badge for its full glossary text.
- **Primary** (filled) buttons perform the main action of a section; outline buttons are secondary.
- Destructive actions (delete) always ask for confirmation.
- Tables scroll horizontally on narrow screens; the page itself stays full width.

---

## 6. Dashboard (operations console)

The dashboard is the engineering operations console. It uses **live database values** — never fabricated demo events. Layout is **full width** of the main content area.

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

Tiles re-flow automatically to the screen width.

### Event trend (7 / 30 / 90 days)

Stacked bars for **Analysed · Review · Issues**. Switch the window with **7d / 30d / 90d**. Leading empty days are trimmed so sparse data stays readable; bars stay centred and a sensible width even with few days.

### Attention required + Data quality

Right-hand stack:

1. **Attention required** — prioritised events (awaiting review/analysis, DQ, high severity, inconclusive). Each row links into the event workspace.
2. **Data quality overview** — donut from real `data_quality` counts (GOOD / ACCEPTABLE / WARNING / POOR / INVALID / …).

### Recent events table

Columns:

Event ID · Date/Time · Substation/Bay · Relay · Fault · **Protection** (e.g. 51N, 87T) · Consistency · RCA · Status · Severity · DQ

Events created by IEC 61850 fetch or auto-fetch appear here exactly like uploaded events.

### Empty database behaviour

When there are zero events:

- All counters show **0**
- Banner: “No disturbance events yet”
- Action: **Open Plant**
- Checklist: Build Plant (SS → kV → Bay → Feeder → IED) → Fetch or upload on IED → Validate → Analyse → Consistency → RCA → Report

No fake demo events are seeded unless you explicitly enable a demo mode (not default).

---

## 7. Recommended workflow (end-to-end)

```text
1.  Open Plant                          (/plant)
2.  Create Substation
3.  Add Voltage level (e.g. 132kV)
4.  Add Bay (e.g. Bay 1 / line1 bay)
5.  Add Feeder
6.  Add IED (relay)                     → Open IED
7.  Bring the record in:
      a) Fetch from IED  → IP + vendor → Test connection → Browse IED
                         → tick record(s) → Fetch & create event
      b) or switch on Auto-fetch new records (server does it on schedule)
      c) or Manual upload → drop CFG+DAT / CFF / ZIP / vendor package
8.  Confirm COMTRADE detection / validation
9.  Setup → Channel map + DR targets (correct if auto-infer looks wrong)
10. Start / Re-run analysis (background — watch the status lamps)
      (fetched events with COMTRADE + settings start automatically)
11. Inspect DR workspace / Waveforms / Sequence
12. Review Electrical + Fault + Location + Protection
13. Study Consistency (setting source!)
14. Study RCA + Evidence (+ cause enrichment if field evidence exists)
15. Download Report (HTML / PDF)
16. Complete Engineer Review
```

Do **not** skip Consistency when RCA looks “confident.” Consistency findings often explain why RCA must stay inconclusive.

After changing **Channel map**, **DR targets**, settings, or **cause evidence**, always **Re-run analysis** so timeline, protection, consistency, and RCA refresh.

Use **All events** for a global view and filters; use **Plant → IED** to bring in records for the correct relay.

---

## 8. Plant hierarchy

Open **Plant** in the sidebar (route `/plant`, breadcrumb “Plant hierarchy”).

### Hierarchy levels

```text
Substation
  └── Voltage level (e.g. 132kV)
        └── Bay (e.g. Bay 1)
              └── Feeder
                    └── IED (relay)  ← fetch / upload + events live here
```

### Level stat cards

Five numbered cards at the top — **1 Substations · 2 Voltage levels · 3 Bays · 4 Feeders · 5 IEDs** — show how many of each exist and remind you of the build order. Each level has its own colour and icon, used again in the tree.

### Adding items

| Level | How to create | Notes |
|-------|---------------|--------|
| **Substation** | **+ Substation** (page header) | Top of the tree |
| **Voltage** | On a substation row → **+ Voltage** | Enter the name and optional **kV** |
| **Bay** | On a voltage row → **+ Bay** | Name the bay clearly (e.g. `line1 bay`) |
| **Feeder** | On a bay row → **+ Feeder** | |
| **IED** | On a feeder row → **+ IED** | Relay / IED name; becomes the fetch/upload target |

Clicking any **+** button opens the **add bar** above the tree: “**New bay** under *132kV*”. Type the name and press **Enter** or **Save**; press **Esc** or **Cancel** to close. The parent row is expanded automatically so you see the new item.

### Working with the tree

| Control | Purpose |
|---------|---------|
| Twisty / row click | Expand or collapse a level |
| **Filter by name or tag** | Shows only matching items (and their parents); expand/collapse buttons are disabled while filtering |
| **Expand all / Collapse all** | Open or close the whole tree |
| **Open** (IED row) | Go to the IED workspace |
| Event count (IED row) | Number of events attached to that relay |
| Delete (trash icon) | Removes the item **and all children** — confirm carefully |

The section header shows “*N IEDs · M events · open an IED to fetch or upload records*”.

When the plant is empty you see **No plant yet** with an **Add first substation** button.

### Naming tips

- Use site names operators recognise (`Substation 2`, `132kV`, `Bay 1`, `Feeder 1`, `IED-4`)
- Prefer verified relay tags — the tag is used in fetched file names (e.g. `iec61850_settings_<tag>.json`)
- Never invent plant topology that does not exist on site

---

## 9. IED workspace

On an IED row click **Open**. The breadcrumb shows **IED workspace**.

### Header

- **Plant path**: Substation › Voltage › Bay › Feeder
- **IED name** as the title
- Chips: relay **Tag**, **kV** (from the voltage level), **IP** (once an IEC 61850 connection has been saved)
- Stats: **Events** (total for this relay) · **In review** · **Last event** (how long ago the newest event occurred)

### Acquire panel — two modes

A segmented switch at the top of the panel selects how records come in:

| Mode | Use when |
|------|---------|
| **Fetch from IED** | The relay is reachable over the network (IEC 61850 / MMS). See [§10](#10-fetching-records-from-the-relay-iec-61850) and [§11](#11-automatic-fetch-auto-fetch) |
| **Manual upload** | You have files exported from the relay tool, e-mail, USB, etc. See [§14](#14-uploading-files-manually) |

**Manual upload** shows a drag-and-drop zone. Dropped or picked files appear as **file chips** (name + size, with × to remove) before you confirm; **Clear N files** empties the list. Clicking **Upload & create event** creates the event under this IED, starts analysis automatically when the package contains COMTRADE **and** settings, and opens the event’s **Files** tab.

### Events for this IED

Below the acquire panel, a list of all events attached to this relay (newest first) with event number, date/time, fault/protection, status and DQ badges. Click a row to open the event workspace.

Events are always created with a **relay_id** (IED). There is no “orphan” upload path in the current UI.

---

## 10. Fetching records from the relay (IEC 61850)

The **Fetch from IED** mode pulls disturbance records straight from the relay using the IEC 61850 **MMS** protocol. It is **read-only**: the platform only reads directory listings, files and data attributes. It never operates controls, never writes settings and never deletes files on the IED.

### 10.1 Prerequisites

| Requirement | Details |
|-------------|---------|
| Network path | The PC running the application must reach the relay IP on **TCP port 102** (MMS). Check firewalls / VLAN routing between the engineering PC and the station bus |
| MMS file services | The relay must allow **file transfer over MMS** (e.g. ABB PCM600: *Communication → IEC 61850 → MMS file transfer*). Without it, settings/status can still be read but records cannot be listed |
| Free client connection | Relays accept a limited number of MMS clients; the SCADA/gateway may already use some |
| Client library | The backend package `pyiec61850-ng` (libiec61850). It is included in `requirements.txt` and in the portable build. If it is missing, the panel shows a warning and the server answers **503** |
| Role | **ANALYST** or higher |

### 10.2 Relay connection

The **Relay connection** block holds:

| Field | Default | Notes |
|-------|---------|-------|
| **IP address** | (empty) | Relay station-bus IP (or host name) |
| **Port** | `102` | Standard MMS port |
| **Vendor** | Auto-detect | Profile that tells the platform where this vendor stores records (see table below) |

After any successful test, browse or fetch, the IP, port and vendor are **saved on the IED** and pre-filled next time. The IP address also appears as a chip in the IED header.

Click **Test connection**. On success the panel shows one line:

```text
Connected to 10.0.0.21:102 · ABB REL670 · fw 2.2.4 · S/N 1234 · profile ABB / Hitachi Energy ·
5 logical device(s) · file services available · 420 ms
```

- **Nameplate** (vendor, model, firmware `fw …`, serial `S/N …`) is read from `LPHD.PhyNam` / `LLN0.NamPlt`
- **profile** is the vendor profile in use — with **Auto-detect** it is chosen from the nameplate
- **file services NOT available** means records cannot be listed or downloaded (settings and status can still be read); the reason is shown underneath
- The IP / port / vendor are saved on the IED

Connection limits: connect timeout **10 s**, per-request timeout **20 s**.

### 10.3 Vendor profiles

| Profile | Families (examples) | Where records are looked for |
|---------|---------------------|------------------------------|
| **Auto-detect (read nameplate)** | Any IEC 61850 Ed1 / Ed2 / Ed2.1 server with MMS file services | `/COMTRADE/` then vendor folders once detected |
| **ABB / Hitachi Energy** | Relion 605/611/615/620/630/640, 650/670 (REL/RED/RET/REB/REC/REF/REM) | `/COMTRADE/`, `/DR/`; events `/EVENTS/` |
| **Siemens** | SIPROTEC 5 (7SA/7SD/7SL/7UT/7SJ/7VK/6MD), SIPROTEC 4 with EN100, Reyrolle 7SR5 | `/COMTRADE/<LD>/`, `/FAULTREC/`, `/REC/`; log `/LOG/` |
| **GE Vernova (Multilin)** | UR / UR+ (D60, L90, T60, F60, B30, C60 …), 8 Series (850/869/889), MiCOM Alstom legacy | `/COMTRADE/`, `/OSCILLOGRAPHY/`, root `OSC*.CFG`; events `/EVENTS/`, `/FAULTREPORT/` |
| **Schneider Electric** | MiCOM Px40 / Agile, Easergy P3/P5, Sepam 80/40 (ACE850) | `/COMTRADE/`, `/DR/`, `/DISTURBANCE/`; events `/EVENTS/`, `/FAULT/` |
| **Schweitzer (SEL)** | SEL-411L/421/487, SEL-751/787, SEL-2440, RTAC | `/COMTRADE/`, `/EVENTS/`; settings `/SETTINGS/` (`SET_*.TXT`) |
| **NR Electric** | PCS-931/902/978/915 | `/COMTRADE/`, `/RECORD/`, `/WAVE/`; events `/EVENT/` |
| **Toshiba** | GRL100 / GRZ100 / GRT100 / GRD200 | `/COMTRADE/` |
| **ZIV / Hitachi Energy Spain** | ZLV / DLX / IDV | `/COMTRADE/`, `/OSCILO/` |
| **Other vendor (generic)** | Ingeteam, Arteche, Efacec, Sifang, XJ, Woodward, Beckwith, Eaton, Hyosung … | `/COMTRADE/`, `/DR/`, `/RECORDS/`; events `/EVENTS/`, `/LOG/` |

The panel shows a short vendor hint (for example the PCM600 file-transfer note for ABB) under the selector.

### 10.4 Browse the records on the relay

Click **Browse IED** (later **Refresh list**). The platform lists the relay’s file store and groups files into disturbance records by base name. The table shows:

| Column | Meaning |
|--------|---------|
| (checkbox) | Select the record(s) to fetch |
| **Record** | Record name (usually the COMTRADE base name) |
| **Recorded** | Date/time from the file store |
| **Files** | Members found (CFG, DAT, HDR, INF, CFF …) |
| **Size** | Total size |
| **Status** | **Complete** (CFG + DAT or CFF present) · **Incomplete** (e.g. DAT missing — cannot be analysed) · **Already fetched** (link to the event created earlier) |

The newest complete record that has not yet been fetched is **pre-selected**. Browsing is limited to about **90 s**; very large file stores may need a vendor profile instead of Auto-detect.

Counts of extra files found (settings files, event files, SCL files) are shown next to the options.

### 10.5 Fetch options

| Option | Default | What it does |
|--------|---------|--------------|
| **Settings (read from data model)** | On | Reads protection settings from the relay data model and any settings files in the file store |
| **Events (protection start/trip status)** | On | Reads start/trip/operate status with timestamps and breaker position, plus event files in the file store |
| **SCL configuration (CID/ICD)** | Off | Downloads the relay’s SCL file if the file store exposes one (kept as an attachment for reference) |
| Description | — | Optional text for the event; default “IEC 61850 fetch from *host:port* — *record*” |

Buttons:

- **Fetch & create event** — one record selected
- **Fetch N records & create events** — several records selected; **one event per record**
- **Fetch settings / events only** — no record selected; creates an event holding just settings and/or status (useful for a settings snapshot)

The whole acquisition is limited to about **240 s**. Warnings (for example a file that could not be read) are listed under “*N warning(s) during fetch*” — the event is still created with whatever was retrieved.

### 10.6 What gets created

For each fetched record the platform creates a new event under this IED (with an `EVT-YYYY-NNNNN` number, see [§12](#12-event-numbers)) and stores:

| File on the event | Content |
|-------------------|---------|
| Record files (`*.cfg`, `*.dat`, `*.hdr`, `*.inf`, `*.cff`) | Exactly as read from the relay — SHA-256 hashed, immutable |
| `iec61850_settings_<tag>.json` | Settings read from the data model, mapped to the platform’s setting blocks (pickups, time dials, curves, zone reaches, CT/VT ratios, enable flags …) plus all raw values under `iec61850_raw` |
| `iec61850_soe_<tag>.csv` | Sequence of events: protection start / trip / operate status changes with IED timestamps and breaker position |
| Vendor settings / event files | Any settings or event files found in the file store (e.g. SEL `SET_*.TXT`) |
| SCL (`*.cid` / `*.icd` / `*.scd`) | Attached for reference when the SCL option is ticked |

How settings are read:

- Logical nodes: protection **P\*** (PDIS, PTOC, PDIF, PTOV, PTUV, …), related **R\*** (RREC, RBRF, RDIR, …), plus **TCTR**, **TVTR**, **XCBR**
- Functional constraints: **SP**, **SG**, **CF** (setting / setting-group / configuration values)
- Active setting group from `LLN0.SGCB.ActSG`
- Values are **as reported by the relay**; nothing is guessed. Unmapped attributes stay in `iec61850_raw` for inspection.

The event date/time is the record time reported by the relay’s file store (the **Recorded** column); if the relay gives none, the fetch time is used. The acquisition details (method IEC 61850 MMS, manual/auto trigger, host, record, nameplate) are stored with the event, and the audit trail logs **`IEC61850_FETCH`**. Auto-fetched events get the description “IEC 61850 auto-fetch from *host:port* — *record*”.

### 10.7 After the fetch

- If exactly **one** event was created, the app opens its **Files** tab.
- If several were created, the IED event list refreshes.
- Events that are **package ready** (COMTRADE **and** settings present) **start analysis automatically**. Events without settings wait for you to add settings (Files tab) and click **Start analysis**.
- Browsing again marks those records as **Already fetched** with a link to their event — you will not create duplicates by accident.

### 10.8 Good practice

- Run **Test connection** first; the nameplate confirms you are talking to the right relay before downloading anything.
- Keep **Settings** ticked: consistency and RCA need the settings that were active when the record was made. Fetch soon after the event if settings might change.
- Always check **Channel map** and **DR targets** on the first event from a new relay type; later events from the same relay usually map the same way.
- If a record shows **Incomplete**, wait a minute (the relay may still be writing it) and **Refresh list**.

---

## 11. Automatic fetch (auto-fetch)

The **Automatic fetch** card (in Fetch from IED mode) lets the server watch the relay and import every **new** disturbance record without anyone opening the page.

### 11.1 Switching it on

1. Enter the **IP address** (and vendor) in Relay connection and preferably run **Test connection** once.
2. Choose the options (below).
3. Turn on **Auto-fetch new records** and pick the interval (**every 1 min, 2 min, 5 min, 10 min, 15 min, 30 min, 1 h, 2 h or 4 h**).

Auto-fetch cannot be enabled without an IP address. Settings are saved immediately on the IED.

### 11.2 Options

| Option | Default | Meaning |
|--------|---------|---------|
| **Settings** | On | Read settings with every new record |
| **Events** | On | Read protection start/trip status with every new record |
| **Start analysis automatically** | On | Queue analysis as soon as the event is created (when COMTRADE + settings are present) |
| **Also import records already on the IED** | Off | Only editable while auto-fetch is **off**. When ticked, the first check imports records that are already stored on the relay too |

### 11.3 How it behaves

- **Baseline:** by default, the first check after switching on only **records what is already on the relay** and imports nothing. From then on, only records that appear later are imported. (Tick *Also import records already on the IED* before switching on if you want the backlog.)
- A background scheduler on the server wakes every **30 s** and checks each IED whose interval has elapsed. Up to **4 IEDs** are checked in parallel.
- Each check imports at most **10 new records**; any remaining ones are picked up on the next check.
- **One event per record**, exactly as with manual fetch, logged in the audit trail as **`IEC61850_AUTO_FETCH`** (user shown as “system”).
- A record that fails to download **3 times** is skipped from then on so one damaged record cannot block the rest.
- Switching auto-fetch off and on again takes a **fresh baseline**.

### 11.4 Status shown on the card

| Line | Meaning |
|------|---------|
| **Last check** | How long ago; with “*N new · M record(s) on IED*” when it succeeded |
| **Next check** | When the scheduler will look again (“within 30 s” right after enabling) |
| **Events created by auto-fetch** | Running total, with the time of the latest one |
| Baseline note | Shown until the first check has run |
| **Last check failed: …** | The error from the last attempt (unreachable, timeout, access denied, …) |
| Scheduler warning | “Background scheduler is not running on the server” — see below |

**Check now** runs a check immediately. If a check for that IED is already running you get “already running” (HTTP 409) — wait for it to finish.

### 11.5 Requirements and limits

- Auto-fetch runs **inside the application server**. It stops when you close the launcher window / shut down the server, and resumes when it starts again.
- The server setting `IEC61850_AUTO_FETCH` (default **true**) enables the scheduler. If it is false, or the IEC 61850 client library is missing, the card shows the scheduler warning — **Check now** still works manually (library permitting).
- Choose sensible intervals: most relays keep a limited number of records; checking every 5–15 min is enough for most sites and keeps load on the relay low.

---

## 12. Event numbers

Every event has a readable, sequential identifier:

```text
EVT-YYYY-NNNNN      e.g.  EVT-2026-00042
```

| Rule | Details |
|------|---------|
| Year | Year the event was created |
| Sequence | Five-digit counter, restarts at `00001` each year |
| Allocation | Automatic for uploads, IEC 61850 fetch and auto-fetch — numbers are never reused within a year |
| Custom IDs | If an event was created with an explicit, meaningful ID (e.g. `EVT-OC-132KV-FEEDER-001` from a package), it is kept |
| Legacy events | Events that had a random (UUID-style) ID from older versions are **renumbered once**, automatically, when the backend starts. The old ID is kept in the event’s extra data as `previous_event_id`, so old reports and notes can still be traced |

Use the event number in search (All events), reports, e-mails and review notes.

---

## 13. All events (list and filters)

Open **Analysis → All events** (route `/events`).

### Header actions

| Control | Purpose |
|---------|---------|
| **Continue …** | Resume last locally remembered event |
| **Open Plant** | Go to hierarchy / fetch / upload |
| **Compare** | Multi-event compare |
| **Clear filters** | Clears search, dates, and dashboard `?queue=` filter |

When you arrive from a Dashboard KPI, a banner shows the active **queue filter** (e.g. Awaiting review).

### Search (live)

Type in **Search**. Matching is case-insensitive across:

- Event number / ID (e.g. `EVT-2026-000`, `00042`)
- Substation / bay / relay (IED)
- Feeder / description (fetched events contain “IEC 61850 fetch from …”)
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
| No events in database | Prompt to open Plant and fetch/upload on an IED |
| Events exist but filters exclude all | “No events match…” + **Clear filters** |

---

## 14. Uploading files manually

### From the IED workspace (primary manual path)

1. **Plant** → expand to the IED → **Open**
2. Select **Manual upload**
3. Optionally type a description; drag and drop files (or click the zone to pick them); check the file chips
4. Click **Upload & create event** — the event is created under that IED, analysis starts if COMTRADE + settings are present, and the Files tab opens
5. Note **SHA-256** on the event **Files** tab (integrity / chain of custody)

Original files are stored **immutably** (content-addressed; not overwritten).

### From the event **Files** tab

After the event exists (uploaded or fetched):

1. Open the event → **Files**
2. Drag and drop additional members (settings, SOE, PDF, …)
3. Confirm upload, then **Re-run analysis**

### Supported extensions

`.cfg .dat .cff .hdr .inf .csv .txt .xml .json .pdf .zip`  
plus vendor / settings packages:  
`.set .rdb .xrio .rio .eve .cev .log .dz5 .dex5 .d5z .pcmi .pcmp`  
and SCL files from IEC 61850 fetch (`.cid .icd .scd`, stored as attachments).

**ZIP packages:** uploading a `.zip` **auto-extracts** the archive. Each allowed member is stored as its own immutable event file. The original ZIP is kept as a **PACKAGE** attachment. Nested ZIPs expand (limited depth). Path-traversal / zip-bomb guards apply.

**Vendor notes (honest):**

| Format | Behaviour |
|--------|-----------|
| SEL `.rdb` | OLE container — SET_ALL text extracted when present → settings ingest |
| SEL `.cev` | Converted to CFG+DAT for waveform / timeline use when convertible |
| DIGSI / PCM600 `.dz5` / `.dex5` / `.d5z` / `.pcmi` / `.pcmp` | Treated as ZIP-like packages when they contain nested COMTRADE / settings / CEV; proprietary non-ZIP blobs stay **NOT CALCULABLE** with export guidance |
| `.set` / `.xrio` / `.rio` / `.eve` / `.log` / SOE CSV | Parsed when structure is recognized; RIO/XRIO supply distance trip-zone geometry for R–X when present |

### Deleting an event

On **All events** → **Delete**, or open an event and click the **trash icon** (Delete event) in the header. Requires **ANALYST** (or higher). Confirm the dialog — the event and related DB records are removed. Stored file blobs remain content-addressed (immutable storage); they are not rewritten. Browser “Continue” memory for that event is cleared.

> Deleting an event that was created by IEC 61850 fetch does not delete anything on the relay.

### Good practice

- Upload **CFG + DAT** together (same base name when possible)
- For CFF, upload the `.cff`
- Or upload a **ZIP** / vendor package containing CFG/DAT/CFF (+ settings / SOE / PDF)
- Upload under the **correct IED** so location / relay columns stay accurate
- After upload, confirm **Channel map** and **DR targets** before trusting protection timing
- Prefer originals from relay software — do not re-save in Excel

---

## 15. COMTRADE detection and validation

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

The system does **not** silently interpolate missing samples or invent channels. Records fetched over IEC 61850 go through exactly the same detection and validation as uploaded ones.

---

## 16. Running analysis

1. After upload/fetch and validation (and preferably after Channel map / DR targets), start analysis from the event header (**Start analysis** / **Re-run analysis**). Fetched events with COMTRADE + settings, and auto-fetched events with *Start analysis automatically* on, are queued for you.
2. The API **queues** the job and returns immediately — engineering runs in the **background** so the browser does not time out.
3. Watch the **Analysis progress** panel and the **status lamps**:

```text
COMTRADE · DATA · SETTINGS · PROTECTION · CONSISTENCY · RCA · REPORT
```

Each lamp is clickable and opens the tab that explains it (e.g. SETTINGS → Consistency / settings view, RCA → RCA tab).

Pipeline stages:

```text
Upload → File Detection → COMTRADE Validation → Parsing →
Signal Processing → Event Reconstruction → Protection Analysis →
Consistency Checker → Fault Classification → RCA → Evidence → Report
```

Stage chips: ✓ completed · ● running · ○ pending · ✕ failed · – skipped. A progress bar shows overall completion. The progress panel is shown **only while a job is queued or running** (or failed); once analysis completes it disappears and the tabs show the results.

On parse/analyse the platform:

- Persists COMTRADE file/channel metadata
- Caches waveform samples for the Waveforms tab
- Applies channel map + digital (DR target) map to electrical / timeline / protection
- Runs consistency and RCA engines (scheme-aware where elements operate)
- Indexes classical similarity features
- Can generate an HTML report artefact

The **Recommended next step** banner guides the engineer (e.g. fix channel map, re-run after FAILED, open DR workspace).

If status is **FAILED**:

- Hover the FAILED badge or open **Details** for the job `error_message`
- Fix COMTRADE / channel map / DR targets / files as indicated
- Click **Re-run analysis**
- Prior results may still be viewable until the new run completes

Typical local analysis for normal records targets **under ~2 minutes**.

---

## 17. Event analysis workspace (detailed)

### Header band

| Element | Content |
|---------|---------|
| Breadcrumb | Substation › Bay › Relay |
| Title | Event number (e.g. `EVT-2026-00042`) and feeder |
| Date pill | Event date/time |
| Badges | Status · data quality · decision |
| Actions | **Share pack** · **Start analysis** / **Re-run analysis** · trash icon (**Delete event**) |
| Status lamps | COMTRADE · DATA · SETTINGS · PROTECTION · CONSISTENCY · RCA · REPORT (clickable) |

Below the band: the **Recommended next step** banner and, while a job runs, the **Analysis progress** panel.

### Tab bar

One tab bar that **stays at the top while you scroll**. Groups on the left, tabs of the selected group on the right:

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

Uploaded / fetched originals, hashes, sizes, types (including extracted ZIP / vendor members and `iec61850_settings_*.json` / `iec61850_soe_*.csv` for fetched events). Add more files here.

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

Chronological reconstruction (inception → pickup → trip → breaker → interruption → reclose/lockout when evidence exists). Digitals follow the **DR targets** map. Missing signals → **NOT AVAILABLE**. External SOE / event-report events merge when parsers succeed — including the **IEC 61850 status SOE** (`iec61850_soe_<tag>.csv`) captured during fetch.

### Electrical

RMS, phasors, sequences, power, impedance, harmonics, etc., each with method/quality. Missing → **NOT CALCULABLE**.

**Impedance / fault resistance table** — shows only the **faulted loop** for the classified fault (e.g. AG → `Z_AG`; ABG → `Z_AB`; ABC → `Z_AB` / `Z_BC` / `Z_CA`). Other loops may be computed internally but are not listed as “the” fault impedance.

**R–X locus** — plotted only when distance / 21 context applies and a fault type is classified. Points are the faulted loop only. **Trip zones** appear when RIO/XRIO geometry or scalar zone reaches are available from settings (never invented).

**Harmonics** — fault-window harmonic bars plus a **time × order heatmap** (short-time DFT) for phase currents when calculable.

**Nominal voltage** — Overview shows kV from the event field; if empty, analysis fills it from settings text, VT ratio, or `…NNNkV…` in filename/station name when present.

### Fault / Location

Fault type / characteristics and distance / location views when inputs exist. Distance never invented — **NOT CALCULABLE** with reason when CT/VT/line/settings are incomplete.

### Protection

Per-element table: Enabled · Pickup · Trip · Expected · Timing · Consistency · Setting source · Evidence.

See also [§18 Protection physics and schemes](#18-protection-physics-and-schemes).

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

Uploaded / fetched settings are **auto-APPROVED** and the active group marked **VERIFIED** by default (see [§20](#20-settings-and-setting-hierarchy)). You can still confirm or re-approve manually if your site policy requires it.

**Mandatory rule:** `51 Enabled = FALSE` with pickup/trip observed → **INCONSISTENT** (typically HIGH). RCA remains **INCONCLUSIVE** regarding relay malfunction until active configuration is verified.

### RCA

Hypothesis board with status CONFIRMED / PROBABLE / POSSIBLE / UNLIKELY / INCONCLUSIVE, score, supporting / contradicting / missing evidence.

Scheme label (when detected) appears in the subtitle (e.g. stepped distance, feeder OC/EF, 87L+21).

**Cause enrichment (field / asset):** use the checkboxes on the RCA page (lightning evidence, vegetation field report, cable asset confirmed, …). Physical causes stay **INCONCLUSIVE** until these structured tokens are saved. After **Save cause evidence**, **Re-run analysis**.

**CONFIRMED** only when evidence requirements are met. Similarity and ML are supporting only. Zone / scheme mismatch → **UNLIKELY** for mismatched asset hypotheses.

**Transformer internal (87T / 87RGF):** CONFIRMED needs differential operate evidence **and** `through_fault_excluded`. The engine asserts through-fault exclusion when Id/Ir operate/restraint supports an internal fault, or (when winding phasors are missing) when 87T operated consistently without phase CT-sat / inrush indicators.

**Decision vs RCA:** A **CONFIRMED** primary hypothesis maps to **ANALYSIS_COMPLETE** unless **material** limitations remain (e.g. phase CT saturation POSSIBLE). Informational notes such as “Merged N external timeline events from SOE” do **not** downgrade the decision to WITH_WARNINGS. A **PROBABLE** primary still yields **ANALYSIS_COMPLETE_WITH_WARNINGS**.

### Evidence

```text
RCA → Hypothesis → Finding → Calculation → Source → Raw data / file
```

### Summary / Report / Review

**Summary** consolidates the event story on a printable sheet. **Report**: see [§23](#23-reports-html-pdf-json). Both always render as a light “paper” page, even in dark theme.

| Review action | When to use |
|--------|-------------|
| **ACCEPT** | Agree with automated findings |
| **MODIFY** | Accept with documented corrections |
| **REJECT** | Reject automated conclusions |
| **INCONCLUSIVE** | Cannot close with available evidence |
| **REQUEST FIELD INVESTIGATION** | Need field verification |

Automated results are retained; overrides are audited separately.

---

## 18. Protection physics and schemes

### Element 51 / 51N / 51P — time overcurrent

When pickup current, time dial (TMS), curve type, and measured current are available, the engine computes expected operate time using IEC/IEEE inverse curves, for example:

- IEC Normal / Very / Extremely / Long-time Inverse  
- IEEE Moderately / Very / Extremely Inverse  

Formula family: `t = TDS × (A / (M^p − 1) + B)` for multiple `M > 1`.

Earth-fault (**51N**) and phase (**51P**) variants use the mapped residual / phase quantities. If inputs are missing → timing physics status **NOT_CALCULABLE**. For fetched events, pickup / time dial / curve come from the relay’s **PTOC** settings.

### Element 67 / 67N / 67P — directional overcurrent

Directional assessments use available voltage/current phasor relationships and settings. Missing polarizing quantity → **UNVERIFIABLE** / **NOT_CALCULABLE**, never invented direction.

### Element 21 — distance

When apparent impedance and zone reach settings exist, a deterministic **mho** (default) or simple **quad** reach check evaluates zone entry. For fetched events, zone reaches come from the relay’s **PDIS** settings.

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

## 19. Understanding status badges and quality labels

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

### IEC 61850 record status (browse table)

Complete · Incomplete · Already fetched

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

## 20. Settings and setting hierarchy

Navigate settings from the event workspace (uploaded / fetched packages) and consistency panels. Version / group priority (highest first):

1. Event-specific active setting  
2. Active setting group  
3. Approved relay base setting  
4. Relay configuration  
5. Historical setting  
6. Engineering design setting  

The UI shows which source was used. The system **never silently picks** a group without displaying it.

### Settings from IEC 61850

When **Settings** is ticked during a fetch, `iec61850_settings_<tag>.json` is created from the relay data model (see [§10.6](#106-what-gets-created)). It is ingested like any other settings file:

- The **active setting group** comes from `LLN0.SGCB.ActSG`, so it is known rather than assumed
- Mapped values feed Protection / Consistency (pickups, time dials, curves, zone reaches, enables, CT/VT ratios)
- Every raw attribute is preserved under `iec61850_raw` for audit
- Vendor settings files found in the file store (e.g. SEL `SET_*.TXT`) are parsed as well

### Auto-approve uploaded settings (default)

When a settings file (JSON / text / vendor extract / `.set` / `.xrio` / `.rio` / IEC 61850 JSON, …) is loaded with the event, the platform treats it as:

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

## 21. Databases (auth vs plant/events)

Local / portable SQLite layout (under `backend\`):

| File | Contents |
|------|----------|
| **`protection_rca_auth.db`** | Users, passwords, auth sessions |
| **`protection_rca_local.db`** | Plant hierarchy, events, event-number counters, IEC 61850 connection + auto-fetch settings per IED, analysis artefacts metadata |

Other folders under `backend\`:

| Folder | Contents |
|--------|----------|
| `storage\` | Immutable file blobs (uploaded and fetched), reports |
| `logs\` | `api-launch.log` — API console output written by the launcher |

### Why two databases?

Clearing plant/event data for a clean engineering trial **does not** wipe logins. You keep `admin` / other accounts while resetting events.

### How to clear data safely

**Events and plant only (keep logins):**

1. Stop `ProtectionRCA.exe`
2. Delete `backend\protection_rca_local.db` (and `-wal` / `-shm` if present)
3. Optionally delete `backend\storage\` event/report blobs
4. Optionally clear browser localStorage key `protection_rca_recent_events_v1` (Continue button)
5. Restart the exe — plant tree and events are empty (IED connections and auto-fetch settings are gone too); event numbers restart at `00001`; log in as before

**Full wipe including users:**

Also delete `backend\protection_rca_auth.db`. Next start recreates bootstrap **`admin` / `admin123`** (or your `BOOTSTRAP_ADMIN_*` values).

Docker / PostgreSQL deployments use the configured application database; auth separation above applies to the local SQLite dual-DB mode.

---

## 22. Rules, models, and historical similarity

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

## 23. Reports (HTML, PDF, JSON)

Open event → **Report**.

| Format | How to get it |
|--------|----------------|
| **JSON** | Structured sections in the report record |
| **HTML** | **Download HTML** — Jinja controlled templates / deterministic fallback |
| **PDF** | **Download PDF** — ReportLab packaging of the engineering content |

The in-app preview is shown as a light page inside the workspace (its styles do not affect the rest of the application, and it stays readable in dark theme).

API:

- `POST /api/reports` with `format`: `JSON` | `HTML` | `PDF`  
- `GET /api/reports/{id}/download`  

Report statements distinguish **OBSERVED / CALCULATED / INFERRED / HYPOTHESIS**. Every conclusion must be traceable to structured data — no LLM prose.

Print remains available via the browser print dialog.

---

## 24. Users, SSO, and audit

### Users

Admins manage accounts and roles under **Users**.

### SSO

See [§3](#3-signing-in-local-and-sso). Configure `AUTH_MODE`, `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `OIDC_AUDIENCE` on the backend.

### Audit

Open **Administration → Audit** (breadcrumb “Audit trail”).

| Column / control | Meaning |
|------------------|---------|
| **When** | Local date/time |
| **User** | Username of whoever performed the action. Automatic actions (e.g. auto-fetch) show **system** |
| **Action** | Colour-coded chip: create = green, upload = blue, analyse = accent, update / review = amber, delete / clear = red, login / export = grey |
| **Object** | Object type and ID (event number, IED, …) |
| **Details** | Old → new values or parameters where applicable |
| Filter box | Filters by user, action, object or details text; the count shows matching entries |

Examples of audited actions:

- Login (local or OIDC)  
- Upload  
- **`IEC61850_FETCH`** — manual fetch (host, records, files)  
- **`IEC61850_AUTO_FETCH`** — event created by auto-fetch  
- Analysis start / complete  
- Setting create / modify  
- Report generate / download  
- Engineer review / approval  
- Manual override  
- Event delete  

Each entry: who / when / what / old→new where applicable.

---

## 25. Supported file types and COMTRADE matrix

| Extension | Typical content |
|-----------|-----------------|
| `.cfg` / `.dat` | COMTRADE configuration + data |
| `.cff` | Combined COMTRADE file |
| `.hdr` / `.inf` | Header / information |
| `.csv` / `.txt` / `.log` | SOE / SER / event reports (when parsers exist), incl. `iec61850_soe_*.csv` |
| `.xml` / `.json` / `.set` / `.xrio` / `.rio` | Settings / configuration / trip-zone exports, incl. `iec61850_settings_*.json` |
| `.rdb` | SEL settings database (SET_ALL extract when present) |
| `.cev` | SEL compressed event — converted to CFG+DAT when convertible |
| `.eve` | Relay event report text (parsed when recognized) |
| `.dz5` / `.dex5` / `.d5z` / `.pcmi` / `.pcmp` | DIGSI / PCM600-style packages (ZIP-expand when possible) |
| `.cid` / `.icd` / `.scd` | IEC 61850 SCL — stored as attachment (reference only) |
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

## 26. Sample / test / golden data

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

Training packages shipped in `portable-share` (each folder = one complete event: CFG + DAT + `relay_settings.json` + `relay_base_settings.txt` + `relay_event_report.txt` + `soe.csv`):

```text
132kV_Feeder_Fault_Events/  EVT-AG-… · EVT-DIFF-… · EVT-DIST-… · EVT-OC-…132KV-FEEDER-001
220kV_Feeder_Fault_Events/  EVT-AG-… · EVT-DIFF-… · EVT-DIST-… · EVT-OC-…220KV-FEEDER-001
```

Use them via **Manual upload** (select all files in one folder, or zip the folder). They cover earth fault (AG), line differential, distance and overcurrent cases.

Regenerate synthetic matrix fixtures:

```bat
cd protection-rca
python scripts\generate_comtrade_fixtures.py
```

Create a plant path ending in an IED, upload test files on that IED, run analysis, and explore each tab.

---

## 27. Engineering language used in reports

Controlled templates only. Examples:

- OBSERVED: trip digital was present  
- CALCULATED: apparent impedance entered Zone 1 reach  
- INFERRED: operation consistent with configured reach  
- HYPOTHESIS: internal feeder fault is probable  

Never treat fluent wording as stronger than status badges.

---

## 28. Frequently asked questions

### General

**Q: Where is Create event / Upload in the menu?**  
A: Removed on purpose. Go to **Plant**, build Substation → Voltage → Bay → Feeder → IED, then **Open** the IED and use **Fetch from IED** or **Manual upload**.

**Q: How do I create my first event?**  
A: Plant → **+ Substation** → **+ Voltage** → **+ Bay** → **+ Feeder** → **+ IED** → **Open** → either Fetch from IED (IP → Test connection → Browse IED → Fetch & create event) or Manual upload (drop CFG/DAT or ZIP → Upload & create event).

**Q: Default login?**  
A: `admin` / `admin123` on a fresh auth database. Change it for production.

**Q: Can the tool trip a breaker or change settings?**  
A: No. OT control is disabled. IEC 61850 access is read-only.

**Q: Does it use ChatGPT?**  
A: No.

### IEC 61850 fetch

**Q: Which relays can I fetch from?**  
A: Any IEC 61850 (Ed1 / Ed2 / Ed2.1) relay that exposes MMS file services — ABB/Hitachi, Siemens, GE, Schneider, SEL, NR, Toshiba, ZIV and others. Pick the vendor profile or leave **Auto-detect**.

**Q: Test connection works but Browse finds no records.**  
A: If Test connection says “file services NOT available”, MMS file transfer is disabled in the relay configuration. Otherwise the records are probably in a vendor-specific folder — select the correct **Vendor** instead of Auto-detect. Also check the relay has actually recorded a disturbance.

**Q: A record shows Incomplete.**  
A: The CFG or DAT is missing (often the relay is still writing it). Wait and **Refresh list**. Incomplete records cannot be analysed.

**Q: Will fetching the same record twice create duplicates?**  
A: The browse list marks it **Already fetched** with a link to the event and does not pre-select it. Auto-fetch never re-imports a record it has already fetched.

**Q: Why did my fetched event not start analysis?**  
A: Automatic start needs both COMTRADE **and** settings. If settings could not be read, add a settings file on the Files tab and click **Start analysis**.

**Q: Does auto-fetch work when I close the browser?**  
A: Yes — it runs in the server. It does **not** run when the launcher/server is stopped.

**Q: I switched on auto-fetch but old records were not imported.**  
A: By design the first check takes a **baseline**. Switch auto-fetch off, tick **Also import records already on the IED**, and switch it on again — or fetch old records manually.

**Q: Which PC connects to the relay when colleagues use the LAN URL?**  
A: The host PC running the application. It needs network access to the relays on port 102.

### Events and numbering

**Q: My old events have new numbers.**  
A: Events with random (UUID) IDs from older versions were renumbered to `EVT-YYYY-NNNNN` at the first start of this version. The old ID is stored as `previous_event_id`.

**Q: I deleted the local DB and cannot log in**  
A: You deleted `protection_rca_auth.db` as well. Restart the app to recreate bootstrap admin, or keep auth DB and only delete `protection_rca_local.db` when clearing events.

**Q: Why are Location / Relay / Fault columns empty?**  
A: Upload / fetch under an IED so plant labels attach; complete analysis for fault / protection columns.

**Q: Search on All events does nothing useful**  
A: Type any fragment of event number, station, bay, relay, fault, or protection code (e.g. `EVT-2026`, `IED-4`, `Bay 1`, `51N`). Use From/To for dates. **Clear filters** resets.

**Q: Can I delete an event?**  
A: Yes — All events **Delete**, or the trash icon in the event header (ANALYST+). Confirm first. Nothing on the relay is affected.

**Q: KPI click does nothing useful**  
A: It opens All events with a queue filter. Use **Clear filters** to reset.

**Q: Continue button still shows a deleted event**  
A: Refresh the page after delete; the app prunes recent-event memory when the event is gone. You can also clear localStorage key `protection_rca_recent_events_v1`.

### Analysis

**Q: Why is RCA INCONCLUSIVE?**  
A: Consistency findings (e.g. disabled 51 operating), or missing evidence for CONFIRMED.

**Q: Why does Decision say WITH_WARNINGS when RCA is CONFIRMED?**  
A: Only **material** warnings downgrade a CONFIRMED case. Re-run analysis on events created with older versions.

**Q: Why does the impedance table show only one Z row?**  
A: By design — only the **faulted loop** for the classified fault.

**Q: Why is Nominal UNKNOWN kV?**  
A: No voltage evidence was found. Upload/fetch settings that state nominal kV (or a VT ratio), then **Re-run analysis**.

**Q: Do I still need to Approve settings?**  
A: Not by default — uploads/fetches are auto-APPROVED / active group VERIFIED. Set `AUTO_APPROVE_UPLOADED_SETTINGS=false` to restore manual approval.

**Q: Fault distance NOT CALCULABLE**  
A: Needs validated CT/VT, line parameters, and impedance model — never invented.

**Q: Waveforms empty**  
A: Run analysis after upload so samples are parsed and cached; check COMTRADE validation.

**Q: Why is analysis FAILED but older results still visible?**  
A: The latest background job failed. Hover FAILED / open Details, fix inputs, **Re-run analysis**.

**Q: Lightning / vegetation / cable stay INCONCLUSIVE**  
A: Protect → **RCA**, tick the matching **cause enrichment** evidence, save, **Re-run analysis**.

**Q: Pickup / trip times look wrong**  
A: Setup → **DR targets**, map the correct digitals (and element), save, re-run.

**Q: Electrical / distance looks wrong after auto-detect**  
A: Setup → **Channel map**, correct roles, save, re-run.

**Q: Can I upload a ZIP of CFG/DAT? SEL `.rdb` / `.cev`? DIGSI / PCM600?**  
A: Yes where extractable (see [§14](#14-uploading-files-manually)). Opaque proprietary blobs stay unsupported — export CFG/DAT from the vendor tool.

**Q: How do I get a PDF?**  
A: Event → Report → **Download PDF**.

### Portable / sharing

**Q: Does the other PC need Python?**  
A: No. `portable-share\python\` contains the complete runtime. Share the whole `portable-share` folder (zipped), not only the exe.

**Q: Can I give only ProtectionRCA.exe to a colleague?**  
A: No. They need the full **`portable-share`** folder (exe + `python` + `backend` + `frontend\dist` + `rules` + `scripts`). Build it with `scripts\build-portable-share.bat`.

**Q: How do others open the app from my laptop?**  
A: Start the exe on your PC, allow Firewall if asked, then they open the **LAN URL** shown in the control window (e.g. `http://192.168.x.x:8001/`). Do not share `127.0.0.1` with them.

**Q: Browser opens 8001 or 5173 — which is correct?**  
A: **8001** = portable (built UI served with the API). **5173** = developer Vite UI. Both use the API on **8001**.

**Q: Closed browser but ports busy**  
A: Close the launcher control window (**Stop & Close**).

**Q: SSO button missing**  
A: OIDC not enabled on the API (`AUTH_MODE` still `local`).

---

## 29. Troubleshooting

### Start-up / portable

| Symptom | What to check |
|---------|----------------|
| Exe says backend/frontend not found | Run `ProtectionRCA.exe` from inside `protection-rca` or `portable-share`; keep `python\`, `backend\`, `frontend\` next to it |
| **“API did not start on port 8001”** | Read the log tail shown in the message, or open `backend\logs\api-launch.log`. Common causes below |
| Log says Python / module not found | The folder is incomplete or from an old build. Rebuild with `scripts\build-portable-share.bat` and copy the **whole** folder again |
| Old build message about a missing base Python / `.venv` | You are running a portable folder built before 0.7.0 (it depended on the builder’s Python). Rebuild — the new build bundles `python\` |
| Log says address already in use | Another copy is running, or another program uses port 8001. Close other `ProtectionRCA.exe` windows (Task Manager if needed) or set `PROTECTION_RCA_PORT` |
| Message mentions a different port (e.g. 8011) | `PROTECTION_RCA_PORT` is set in the environment. Remove it or open that port’s URL |
| First start very slow / times out | Antivirus scanning `python\` on first launch. Wait and start again; add an exclusion if allowed |
| Database locked | Another process has `protection_rca_local.db` open (second copy, sync tool such as OneDrive). Close it / move the folder out of synced locations |
| UI blank / API errors | http://127.0.0.1:8001/health |
| Colleague cannot open LAN URL | Same Wi-Fi/LAN; use host IP not 127.0.0.1; allow Windows Firewall private network for port **8001** |
| Exe rebuild “Access denied” / false “EXE OK” | Close all `ProtectionRCA.exe` windows. Prefer `scripts\build-all-latest.bat` — it kills locked processes and fails if PyInstaller cannot write the EXE |
| Build stops at “bundled Python check failed” | The builder machine’s `backend\.venv` is missing packages. Run `pip install -r backend\requirements.txt` in the venv and rebuild |

### IEC 61850 fetch

| Symptom | What to check |
|---------|----------------|
| Panel warns the IEC 61850 library is missing / HTTP **503** | Install `pyiec61850-ng` in the backend environment (`pip install -r backend\requirements.txt`) or use a current portable build |
| **Test connection** times out / refused (HTTP **502**) | Wrong IP; relay not reachable (ping, VLAN, firewall); TCP **102** blocked; relay’s MMS client slots all in use; relay IEC 61850 server disabled |
| Access denied / authentication error | Relay requires MMS authentication or restricts clients by IP — allow the host PC’s IP in the relay configuration |
| Browse finds no records | Enable **MMS file transfer** in the relay tool (e.g. PCM600); choose the correct **Vendor** profile; confirm the relay has records |
| Browse takes very long / times out (~90 s) | Large file store — choose the vendor profile instead of Auto-detect |
| Record **Incomplete** | CFG/DAT missing or still being written — **Refresh list** later |
| Fetch completes with warnings | Open “*N warning(s) during fetch*” — typical: one file unreadable, settings node not present. The event holds whatever was retrieved |
| “Nothing was retrieved from the IED” (404) | No selected record and nothing readable for settings/events. Check file transfer and the vendor profile |
| Settings JSON almost empty | Relay exposes few settings via the data model (some vendors keep them only in their tool). Upload the vendor settings export on the Files tab |
| Event did not auto-analyse | Settings missing → add settings, **Start analysis** |

### Auto-fetch

| Symptom | What to check |
|---------|----------------|
| “Enter the IED IP address before enabling auto-fetch” | Fill IP in Relay connection first |
| “Background scheduler is not running on the server” | `IEC61850_AUTO_FETCH` is false or the library is missing. Use **Check now** meanwhile |
| Nothing imported after enabling | Expected on the first check (baseline). New records after that are imported. Use *Also import records already on the IED* for backlog |
| **Last check failed: …** | Same causes as Test connection; auto-fetch retries on the next interval |
| A record is never imported | It failed 3 times and is skipped — fetch it manually to see the warning |
| “already running” on Check now (409) | A check for that IED is in progress; wait |
| Auto-fetch stopped overnight | The launcher / PC was closed or went to sleep — auto-fetch only runs while the server runs |

### Analysis and data

| Symptom | What to check |
|---------|----------------|
| Cannot log in after DB clear | Ensure `protection_rca_auth.db` exists or restart for bootstrap `admin` / `admin123` |
| No Create event menu | Use **Plant → IED → Fetch from IED / Manual upload** |
| Search finds nothing unexpected | Clear filters; confirm spelling; protection codes like `87T` are searchable |
| Date filter misses events | Leave To at 00:00 to include whole day; times are local |
| Settings NOT VERIFIED / WITH_WARNINGS on old events | **Re-run analysis** after upgrading |
| Upload rejected | Extension, size limit, or role; upload from IED workspace or event Files |
| COMTRADE INVALID | Fix source export; do not force confident RCA |
| Analysis FAILED | Hover FAILED for `error_message`; fix Channel map / DR targets / files; **Re-run**; restart exe after backend updates |
| Stuck “Queued (background)” with FAILED | Latest job never advanced — re-run after fix; check `backend\logs\api-launch.log` |
| Waveforms empty | Analysis/parse not run or validation failed |
| Wrong pickup/trip sequence | Setup → **DR targets** → save → re-run |
| Wrong phasors / distance | Setup → **Channel map** → save → re-run |
| Consistency empty | Analysis not run or no digital/setting inputs |
| Vendor `.rdb` / `.cev` / DIGSI unused | Confirm extract succeeded on Files tab; else export CFG/DAT + settings text from vendor tool |
| PDF download fails | Ensure `reportlab` installed in backend env (included in portable build) |
| Report shows “Report template NOT AVAILABLE” | The `templates\` folder is missing next to `backend\` (portable folders built before this fix). Rebuild `portable-share` or copy `protection-rca\templates` into it, restart the exe, then click **Refresh report** |
| Cannot review | Role below PROTECTION_ENGINEER / APPROVER |
| Audit shows “system” | Automatic action (e.g. auto-fetch) — not a missing user |

API docs: http://127.0.0.1:8001/docs

---

## 30. Where to find more documentation

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

IEC 61850 REST endpoints (see `/docs` for schemas):

| Method + path | Purpose |
|---------------|---------|
| `GET /api/iec61850/info` | Library availability, vendor profiles |
| `GET` / `PUT /api/ieds/{id}/iec61850` | Saved connection (IP, port, vendor) |
| `POST /api/ieds/{id}/iec61850/test` | Connect + nameplate |
| `POST /api/ieds/{id}/iec61850/browse` | List records |
| `POST /api/ieds/{id}/iec61850/fetch` | Fetch and create event(s) |
| `GET` / `PUT /api/ieds/{id}/iec61850/auto-fetch` | Auto-fetch settings and status |
| `POST /api/ieds/{id}/iec61850/auto-fetch/run-now` | Check now |

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

## 31. Quick reference card

```text
START      → Double-click ProtectionRCA.exe (portable: :8001 · dev: :5173)
STOP       → Close launcher control window
SHARE      → scripts\build-portable-share.bat → zip whole portable-share\
             (Python bundled — nothing to install on the other PC)
API FAIL   → Read log tail / backend\logs\api-launch.log
LAN        → Others open http://<host-IP>:8001/ (Firewall allow)
LOGIN      → admin / admin123 (bootstrap) or SSO if configured
PLANT      → Substation → Voltage → Bay → Feeder → IED → Open
FETCH      → IED → Fetch from IED → IP/Vendor → Test → Browse → tick → Fetch & create event
AUTO       → IED → Auto-fetch new records → interval → (baseline first check)
UPLOAD     → IED → Manual upload → drop CFG/DAT/CFF/ZIP/vendor → Upload & create event
EVENT ID   → EVT-YYYY-NNNNN (auto) · legacy UUID → previous_event_id
MAP        → Setup → Channel map + DR targets → save
ANALYSE    → Start / Re-run analysis (background) → watch status lamps
VERIFY     → Waveforms → Sequence → Consistency → RCA → Evidence
CAUSE      → RCA cause enrichment (field evidence) → re-run
FILTER     → All events: Search + From/To + Clear filters
REPORT     → Download HTML or PDF
CLOSE-OUT  → Review (ACCEPT / MODIFY / REJECT / …)
DELETE     → All events → Delete, or trash icon in event header (ANALYST+)
AUDIT      → Administration → Audit (filter; "system" = automatic)
DBS        → auth.db = users · local.db = plant/events/IED connections
REMEMBER   → Read-only IEC 61850 · No invented data · No OT control · No generative AI
```

---

*End of User Guide — Protection RCA Platform (document version 0.7.0)*
