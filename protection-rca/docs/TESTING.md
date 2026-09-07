# Testing

## Layout

| Area | Location | Runner |
|------|----------|--------|
| Backend unit / engineering | `backend/tests/` | pytest |
| Frontend component | `frontend/tests/` | vitest |
| COMTRADE fixtures | `test_data/comtrade/` | consumed by pytest |
| Golden expectations | `test_data/golden/` | regression reference |

## Backend tests

Current modules:

- `test_comtrade_detector.py` — version/format/container detection
- `test_comtrade_parser.py` — IEEE 1999 fixture parse, scaling, timestamps, validation
- `test_signal_processing.py` — phasors, harmonics, impedance `NOT_CALCULABLE` paths
- `test_fault_classification.py` — fault types / inconclusive / distance gates
- `test_consistency.py` — **51 enabled=false** critical rule
- `test_rca.py` — hypothesis gating / forced inconclusive / setting verification

Run from repo (preferred):

```bash
# Bash / Git Bash / WSL
./scripts/run_tests.sh

# PowerShell
./scripts/run_tests.ps1
```

Or manually:

```bash
cd backend
set PYTHONPATH=.
pytest -q
# with coverage:
pytest --cov=app --cov=comtrade --cov=consistency --cov=protection --cov=rca --cov=fault_analysis -q
```

Use `RUN_ANALYSIS_SYNC=true` when exercising API analysis without a Celery worker.

## Frontend tests

```bash
cd frontend
npm test
```

Examples: `LoginPage.test.tsx`, `ConsistencyPage.test.tsx`.

## Fixtures

Primary validated fixture:

- `test_data/comtrade/ieee_1999/ag_fault.cfg`
- `test_data/comtrade/ieee_1999/ag_fault.dat`

Additional directories reserved for CFF, IEEE 2013, and malformed negative cases: `test_data/comtrade/{cff,ieee_2013,malformed}/`.

Golden case `EVT-SYNTH-AG-001` documents expected parse/classification outcomes — see `test_data/golden/README.md`.

## What to assert in new tests

- Partial support statuses for IEEE 1991 and `nrates > 1` (never assert “fully validated”)
- `NOT_CALCULABLE` / `NOT AVAILABLE` / `INCONCLUSIVE` when inputs missing
- Critical consistency → `rca_must_remain_inconclusive`
- No silent mutation of COMTRADE records during validation

## CI suggestions

1. Install backend requirements + run pytest  
2. `npm ci && npm test && npm run build` for frontend  
3. Optional: `docker compose config` / build smoke  

Keep secrets out of CI logs; use disposable DB (SQLite/`aiosqlite` is available for some unit contexts where configured).
