"""
Full webapp API verification — every major UI surface / tab.

Runs in-process (ASGI + temp SQLite). Does not leave servers running.
Uses Proper_COMTRADE_AG_Fault_Test_Event.zip when present on disk.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import traceback
from pathlib import Path

# --- isolate env BEFORE importing app ---
TMP = Path(tempfile.mkdtemp(prefix="prc_verify_"))
DB = TMP / "verify.db"
STORE = TMP / "storage"
STORE.mkdir(parents=True, exist_ok=True)

os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{DB.as_posix()}"
os.environ["BOOTSTRAP_ADMIN_USERNAME"] = "admin"
os.environ["BOOTSTRAP_ADMIN_PASSWORD"] = "VerifyAdmin123!"
os.environ["BOOTSTRAP_ADMIN_EMAIL"] = "admin@verify.local"
os.environ["APP_ENV"] = "development"
os.environ["RUN_ANALYSIS_SYNC"] = "true"
os.environ["STORAGE_BACKEND"] = "local"
os.environ["LOCAL_STORAGE_PATH"] = str(STORE)
os.environ["SECRET_KEY"] = "verify-only-secret"
os.environ["CORS_ORIGINS"] = "http://127.0.0.1:5173,http://localhost:5173"

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

TEST_ZIP = Path(
    r"c:\Users\5863.AVAADA\Downloads\Proper_COMTRADE_AG_Fault_Test_Event.zip"
)
TEST_ZIP_FALLBACK = Path(
    r"c:\Users\5863.AVAADA\Downloads\Protection_RCA_COMTRADE_Test_Pack"
    r"\protection_rca_test_samples\EVT-TEST-001.zip"
)
REPO_ZIP = BACKEND.parent / "test_data" / "Proper_COMTRADE_AG_Fault_Test_Event.zip"
FIXTURE_CFG = BACKEND.parent / "test_data" / "comtrade" / "ieee_1999" / "ag_fault.cfg"
FIXTURE_DAT = BACKEND.parent / "test_data" / "comtrade" / "ieee_1999" / "ag_fault.dat"

PASS: list[str] = []
FAIL: list[str] = []


def ok(name: str, detail: str = "") -> None:
    PASS.append(name)
    print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))


def bad(name: str, detail: str) -> None:
    FAIL.append(name)
    print(f"  FAIL  {name} — {detail}")


async def main() -> int:
    from app.core.config import get_settings

    get_settings.cache_clear()

    # Rebuild DB engine against isolated URL
    import app.database as dbmod
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    await dbmod.engine.dispose()
    dbmod.engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
    dbmod.AsyncSessionLocal = async_sessionmaker(
        dbmod.engine, class_=AsyncSession, expire_on_commit=False
    )

    from app.database import init_db
    from app.services.seed import seed_if_empty

    await init_db()
    await seed_if_empty()

    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    app = create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # ---------- Health / Auth ----------
        r = await client.get("/api/health")
        (ok if r.status_code == 200 and r.json().get("status") == "ok" else bad)(
            "health", r.text if r.status_code != 200 else ""
        )

        r = await client.get("/api/auth/mode")
        (ok if r.status_code == 200 else bad)("auth.mode", r.text)

        r = await client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "VerifyAdmin123!"},
        )
        if r.status_code != 200:
            bad("auth.login", r.text)
            print("\nCannot continue without login.")
            return 1
        token = r.json()["access_token"]
        ok("auth.login", f"role={r.json().get('role')}")
        h = {"Authorization": f"Bearer {token}"}

        r = await client.get("/api/users/me", headers=h)
        (ok if r.status_code == 200 else bad)("users.me", r.text)

        # ---------- Operations / plant / engineering lists ----------
        for name, path in [
            ("dashboard.stats", "/api/dashboard/stats?days=30"),
            ("events.list", "/api/events"),
            ("substations.list", "/api/substations"),
            ("bays.list", "/api/bays"),
            ("relays.list", "/api/relays"),
            ("breakers.list", "/api/breakers"),
            ("assets.list", "/api/assets"),
            ("settings.list", "/api/settings"),
            ("rules.list", "/api/rules"),
            ("models.list", "/api/models"),
            ("users.list", "/api/users"),
            ("audit.list", "/api/audit"),
        ]:
            r = await client.get(path, headers=h)
            (ok if r.status_code == 200 else bad)(name, f"{r.status_code} {r.text[:200]}")

        # ---------- Create plant assets (CRUD smoke) ----------
        r = await client.post(
            "/api/substations",
            headers=h,
            json={"name": "VERIFY_SS", "code": "VSS1", "voltage_levels_kv": [132]},
        )
        if r.status_code in (200, 201):
            ss_id = r.json()["id"]
            ok("substations.create")
        else:
            bad("substations.create", r.text[:300])
            ss_id = None

        # ---------- Event + ZIP/COMTRADE upload + all tabs ----------
        r = await client.post(
            "/api/events",
            headers=h,
            json={
                "event_id": "EVT-VERIFY-001",
                "description": "Full webapp verification",
                "event_datetime": "2026-09-04T08:00:00Z",
                "substation_name": "TEST_SUBSTATION",
                "bay_name": "BAY-1",
                "relay_tag": "RELAY_TEST",
                "nominal_frequency_hz": 50,
            },
        )
        if r.status_code not in (200, 201):
            bad("events.create", r.text[:400])
            return 1
        event = r.json()
        eid = event["id"]
        ok("events.create", event.get("event_id"))

        # Upload package — prefer Proper AG fault ZIP
        files_payload = []
        zip_path = next(
            (p for p in (TEST_ZIP, REPO_ZIP, TEST_ZIP_FALLBACK) if p.is_file()),
            None,
        )
        if zip_path is not None:
            files_payload = [
                ("files", (zip_path.name, zip_path.read_bytes(), "application/zip"))
            ]
            ok("fixture.zip", str(zip_path))
        elif FIXTURE_CFG.is_file() and FIXTURE_DAT.is_file():
            files_payload = [
                ("files", ("ag_fault.cfg", FIXTURE_CFG.read_bytes(), "text/plain")),
                ("files", ("ag_fault.dat", FIXTURE_DAT.read_bytes(), "application/octet-stream")),
            ]
            ok("fixture.cfgdat", "ieee_1999 ag_fault")
        else:
            bad("fixture", "No Proper AG ZIP or golden CFG/DAT found")
            return 1

        r = await client.post(f"/api/events/{eid}/files", headers=h, files=files_payload)
        if r.status_code not in (200, 201):
            bad("files.upload", r.text[:500])
            return 1
        uploaded = r.json()
        names = [f.get("original_filename") for f in uploaded]
        has_cfg = any(str(n).lower().endswith(".cfg") for n in names)
        has_dat = any(str(n).lower().endswith(".dat") for n in names)
        has_settings = any(str(n).lower().endswith("relay_settings.json") or str(n).lower() == "relay_settings.json" for n in names)
        if has_cfg and has_dat:
            ok(
                "files.upload.extract",
                f"{len(uploaded)} files: {names}"
                + (" +settings" if has_settings else ""),
            )
        else:
            bad("files.upload.extract", f"missing cfg/dat in {names}")

        # COMTRADE detect/validate with uploaded bytes
        if zip_path is not None:
            det_files = [("files", (zip_path.name, zip_path.read_bytes(), "application/zip"))]
        else:
            det_files = [
                ("files", ("ag_fault.cfg", FIXTURE_CFG.read_bytes(), "text/plain")),
                ("files", ("ag_fault.dat", FIXTURE_DAT.read_bytes(), "application/octet-stream")),
            ]
        r = await client.post("/api/comtrade/detect", headers=h, files=det_files)
        (ok if r.status_code == 200 and r.json().get("is_comtrade") else bad)(
            "comtrade.detect", r.text[:300]
        )
        r = await client.post("/api/comtrade/validate", headers=h, files=det_files)
        (ok if r.status_code == 200 else bad)("comtrade.validate", r.text[:300])

        # Start analysis (sync in development)
        r = await client.post(
            "/api/analyse",
            headers=h,
            json={"event_id": eid, "force": True},
        )
        if r.status_code not in (200, 201):
            bad("analyse.start", r.text[:500])
            return 1
        job = r.json().get("job") or {}
        ok("analyse.start", f"status={job.get('status')} progress={job.get('progress')}")
        if job.get("status") not in ("COMPLETED", "RUNNING", "PENDING"):
            bad("analyse.status", str(job))
        elif job.get("status") == "COMPLETED":
            ok("analyse.completed")
        else:
            # Deferred analyse — wait for background job (COMTRADE can take a bit)
            for _ in range(90):
                await asyncio.sleep(0.5)
                st = await client.get(f"/api/events/{eid}/analysis-status", headers=h)
                if st.status_code == 200 and st.json().get("status") == "COMPLETED":
                    ok("analyse.completed")
                    break
                if st.status_code == 200 and st.json().get("status") == "FAILED":
                    bad("analyse.completed", st.text[:400])
                    break
            else:
                bad("analyse.completed", st.text[:300] if st else "timeout")

        # ---- Event workspace tabs (API behind each tab) ----
        tab_checks = [
            ("tab.overview", "GET", f"/api/events/{eid}", None),
            ("tab.files", "GET", f"/api/events/{eid}/files", None),
            ("tab.comtrade", "GET", f"/api/events/{eid}/comtrade", None),
            ("tab.waveforms", "GET", f"/api/events/{eid}/waveforms", None),
            ("tab.timeline", "GET", f"/api/events/{eid}/timeline", None),
            ("tab.electrical", "GET", f"/api/events/{eid}/electrical", None),
            ("tab.protection", "GET", f"/api/events/{eid}/protection", None),
            ("tab.consistency", "GET", f"/api/events/{eid}/consistency", None),
            ("tab.fault", "GET", f"/api/events/{eid}/fault", None),
            ("tab.rca", "GET", f"/api/events/{eid}/rca", None),
            ("tab.evidence", "GET", f"/api/events/{eid}/evidence", None),
            ("tab.report.list", "GET", f"/api/reports/by-event/{eid}", None),
            ("tab.analysis-status", "GET", f"/api/events/{eid}/analysis-status", None),
        ]
        results: dict[str, object] = {}
        for name, method, path, body in tab_checks:
            if method == "GET":
                r = await client.get(path, headers=h)
            else:
                r = await client.post(path, headers=h, json=body)
            if r.status_code != 200:
                bad(name, f"{r.status_code} {r.text[:300]}")
                continue
            results[name] = r.json()
            ok(name)

        # Deep assertions for critical tabs
        ct = results.get("tab.comtrade")
        if isinstance(ct, dict):
            if ct.get("start_timestamp") and ct.get("trigger_timestamp"):
                ok("comtrade.timestamps", f"{ct.get('start_timestamp')} / {ct.get('trigger_timestamp')}")
            else:
                bad(
                    "comtrade.timestamps",
                    f"start={ct.get('start_timestamp')} trigger={ct.get('trigger_timestamp')}",
                )
            if (ct.get("analog_channel_count") or 0) >= 1 and (ct.get("total_samples") or 0) > 0:
                ok(
                    "comtrade.channels",
                    f"A={ct.get('analog_channel_count')} D={ct.get('digital_channel_count')} N={ct.get('total_samples')}",
                )
            else:
                bad("comtrade.channels", str(ct)[:200])

        fault = results.get("tab.fault")
        if isinstance(fault, list) and fault:
            ft = fault[0].get("fault_type")
            if ft and ft != "UNKNOWN":
                ok("fault.classified", f"{ft} / {fault[0].get('status')}")
                if zip_path and "Proper_COMTRADE_AG" in zip_path.name and "A" not in str(ft).upper():
                    bad("fault.ag_expected", f"expected AG-family from Proper ZIP, got {ft}")
                elif zip_path and "Proper_COMTRADE_AG" in zip_path.name:
                    ok("fault.ag_expected", str(ft))
            else:
                bad("fault.classified", str(fault[0])[:200])
        elif isinstance(fault, dict) and fault.get("fault_type") not in (None, "UNKNOWN"):
            ft = fault.get("fault_type")
            ok("fault.classified", str(ft))
            if zip_path and "Proper_COMTRADE_AG" in zip_path.name:
                if "A" in str(ft).upper() and ("G" in str(ft).upper() or "N" in str(ft).upper() or str(ft).upper() in ("AG", "AN", "A-G")):
                    ok("fault.ag_expected", str(ft))
                else:
                    bad("fault.ag_expected", f"expected AG-family, got {ft}")
        else:
            bad("fault.classified", str(fault)[:200])

        wf = results.get("tab.waveforms")
        if isinstance(wf, dict):
            chans = wf.get("channels") or []
            if len(chans) >= 1 and any((c.get("samples") or []) for c in chans):
                ok("waveforms.samples", f"{len(chans)} channels")
            else:
                bad("waveforms.samples", f"channels={len(chans)}")

        rca = results.get("tab.rca")
        if isinstance(rca, dict):
            hyps = rca.get("hypotheses") or []
            ok("rca.hypotheses", f"count={len(hyps)} decision={rca.get('decision_state')}")

        cons = results.get("tab.consistency")
        if isinstance(cons, dict):
            ok(
                "consistency.payload",
                f"overall={cons.get('overall_status')} findings={len(cons.get('findings') or [])}",
            )

        ev = results.get("tab.evidence")
        if isinstance(ev, dict) and "items" in ev:
            ok("evidence.items.shape", f"count={len(ev.get('items') or [])}")
        elif isinstance(ev, list):
            ok("evidence.list.shape", f"count={len(ev)}")
        else:
            bad("evidence.shape", str(type(ev)))

        # Report generate HTML + PDF
        for fmt in ("HTML", "PDF", "JSON"):
            r = await client.post(
                "/api/reports",
                headers=h,
                json={"event_id": eid, "report_type": "RCA", "format": fmt},
            )
            if r.status_code not in (200, 201):
                bad(f"report.generate.{fmt}", r.text[:300])
                continue
            rid = r.json().get("id")
            ok(f"report.generate.{fmt}", rid)
            if rid and fmt in ("HTML", "PDF"):
                d = await client.get(f"/api/reports/{rid}/download", headers=h)
                if d.status_code != 200 or len(d.content) <= 20:
                    bad(f"report.download.{fmt}", f"{d.status_code} len={len(d.content)}")
                elif fmt == "PDF" and not d.content.startswith(b"%PDF"):
                    bad(
                        f"report.download.{fmt}",
                        f"not a PDF (got {d.headers.get('content-type')} head={d.content[:20]!r})",
                    )
                else:
                    ok(f"report.download.{fmt}", f"{len(d.content)} bytes")

        r = await client.get(f"/api/reports/by-event/{eid}", headers=h)
        if r.status_code == 200 and (r.json().get("items") or []):
            ok("report.list.has_items", f"total={r.json().get('total')}")
        else:
            bad("report.list.has_items", r.text[:200])

        # Engineer review
        r = await client.post(
            "/api/review",
            headers=h,
            json={
                "event_id": eid,
                "action": "ACCEPT",
                "comments": "Verification accept",
            },
        )
        (ok if r.status_code in (200, 201) else bad)("review.submit", r.text[:300])

        r = await client.get(f"/api/review/event/{eid}", headers=h)
        (ok if r.status_code == 200 else bad)("review.list", r.text[:200])

        # Event patch + delete smoke (create disposable)
        r = await client.post(
            "/api/events",
            headers=h,
            json={"event_id": "EVT-DELETE-ME", "description": "temp"},
        )
        if r.status_code in (200, 201):
            del_id = r.json()["id"]
            d = await client.delete(f"/api/events/{del_id}", headers=h)
            (ok if d.status_code in (200, 204) else bad)("events.delete", d.text[:200])
        else:
            bad("events.create_for_delete", r.text[:200])

        # Dashboard after data
        r = await client.get("/api/dashboard/stats?days=30", headers=h)
        if r.status_code == 200 and int(r.json().get("total_events") or 0) >= 1:
            ok("dashboard.after_data", f"total={r.json().get('total_events')}")
        else:
            bad("dashboard.after_data", r.text[:200])

    print("\n======== SUMMARY ========")
    print(f"PASS: {len(PASS)}")
    print(f"FAIL: {len(FAIL)}")
    if FAIL:
        print("Failed checks:")
        for f in FAIL:
            print(f"  - {f}")
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception:
        traceback.print_exc()
        raise SystemExit(2)
