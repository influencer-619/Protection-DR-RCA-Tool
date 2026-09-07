#!/usr/bin/env python3
"""
Optional demo seed helper for Protection RCA.

The API already seeds an empty database on startup (admin/admin123, sample
assets, demo event) via ``app.services.seed.seed_if_empty``.

This script is for operators who want to:
  - force-print default credentials / connection hints
  - optionally insert an extra tagged demo event when the API is running

Usage (from repo root)::

    python scripts/seed_demo.py
    python scripts/seed_demo.py --api http://localhost:8000 --username admin --password admin123

Requires: Python 3.11+, httpx (installed with backend requirements).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone


DEFAULT_USERS = (
    ("admin", "admin123", "ADMIN"),
    ("analyst", "analyst123", "ANALYST"),
    ("engineer", "engineer123", "PROTECTION_ENGINEER"),
)


def print_local_defaults() -> None:
    print("Protection RCA — local demo defaults")
    print("=" * 50)
    print("Frontend:  http://localhost:5173")
    print("API docs:  http://localhost:8000/docs")
    print("Health:    http://localhost:8000/health")
    print()
    print("Seeded users (created automatically when DB is empty):")
    for u, p, r in DEFAULT_USERS:
        print(f"  {u:12} / {p:14}  [{r}]")
    print()
    print("Postgres:  protection / protection_dev_only @ protection_rca")
    print("MinIO:     minioadmin / minioadmin  bucket=protection-rca")
    print()
    print("COMTRADE fixture: test_data/comtrade/ieee_1999/ag_fault.{cfg,dat}")
    print("Golden case:      test_data/golden/EVT-SYNTH-AG-001/")
    print()
    print("Note: generative AI is not used. OT control plane is disabled.")


def seed_via_api(base: str, username: str, password: str) -> int:
    try:
        import httpx
    except ImportError:
        print("httpx not installed — run from backend venv or pip install httpx", file=sys.stderr)
        return 1

    base = base.rstrip("/")
    with httpx.Client(timeout=60.0) as client:
        r = client.post(f"{base}/api/auth/login", json={"username": username, "password": password})
        if r.status_code != 200:
            print(f"Login failed: {r.status_code} {r.text}", file=sys.stderr)
            return 1
        token = r.json().get("access_token")
        if not token:
            print("Login response missing access_token", file=sys.stderr)
            return 1
        headers = {"Authorization": f"Bearer {token}"}

        body = {
            "description": "Optional seed_demo.py event",
            "event_datetime": datetime.now(timezone.utc).isoformat(),
            "nominal_voltage_kv": 220.0,
            "nominal_frequency_hz": 50.0,
            "feeder": "FEEDER-A",
            "tags": ["demo", "seed_demo_script"],
        }
        er = client.post(f"{base}/api/events", headers=headers, json=body)
        if er.status_code not in (200, 201):
            print(f"Create event failed: {er.status_code} {er.text}", file=sys.stderr)
            return 1
        event = er.json()
        print("Created event:")
        print(json.dumps({"id": event.get("id"), "event_id": event.get("event_id"), "status": event.get("status")}, indent=2))
        print()
        print("Next: upload test_data/comtrade/ieee_1999/ag_fault.cfg and .dat")
        print(f"  POST {base}/api/events/{event.get('id')}/files")
        print(f"  then POST {base}/api/analyse  with event_id")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Protection RCA optional demo seed helper")
    parser.add_argument("--api", default="", help="If set, login and create an extra demo event")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="admin123")
    args = parser.parse_args()

    print_local_defaults()
    if args.api:
        return seed_via_api(args.api, args.username, args.password)
    print("Tip: pass --api http://localhost:8000 to create an extra demo event via the API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
