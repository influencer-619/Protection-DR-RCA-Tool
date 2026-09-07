# Consistency checker

## Role

The consistency engine (`backend/consistency/`) runs **after** protection assessment and **before** RCA. It compares observed protection behaviour to applicable settings and sequence expectations.

Primary classes:

- `ConsistencyEngine` — orchestration (`engine.py`)
- Check implementations — `checker.py`
- Findings — `findings.py`
- Rule catalogue — `rules/consistency/core_checks.yaml`

## Finding statuses

| Status | Meaning |
|--------|---------|
| `CONSISTENT` | Observed matches expected |
| `INCONSISTENT` | Conflict requiring investigation |
| `UNVERIFIABLE` | Insufficient data (do not invent a conclusion) |
| `DATA_QUALITY_ISSUE` | Input quality blocks verification |

Severities: `INFO` … `CRITICAL`.

## Core per-element checks

For each `ProtectionAssessment`:

1. **enabled_vs_pickup** — `enabled=FALSE` and `pickup=TRUE` → `INCONSISTENT` (HIGH)  
2. **enabled_vs_trip** — `enabled=FALSE` and `trip=TRUE` → `INCONSISTENT` (**CRITICAL**)  
3. **pickup_vs_trip** — `trip=TRUE` and `pickup=FALSE` → `INCONSISTENT` (HIGH; may be instantaneous path / mapping issue)

Incomplete enabled/pickup/trip → `UNVERIFIABLE` with confidence `INCONCLUSIVE`.

## Critical rule: 51 enabled = false

Catalogue id: **`CONS-CRITICAL-51-DISABLED-OPERATE`**

> If element **51** (and by the same checker logic, any element) has `enabled=FALSE` but **pickup and/or trip TRUE**, mark **INCONSISTENT**, attach investigation hints, and force **RCA to remain INCONCLUSIVE** until the active configuration is verified.  
> **Do NOT auto-conclude relay malfunction.**

Implementation details:

- `ConsistencyEngine` sets `has_critical_setting_inconsistency=True` and `rca_must_remain_inconclusive=True` when any finding has status `INCONSISTENT`, check type `enabled_vs_pickup` or `enabled_vs_trip`, and observed text contains `enabled=FALSE`.
- Explanations explicitly warn against auto-concluding malfunction.
- Investigation hints include: wrong/stale base setting, different active setting group, setting changed before event, incorrect event–setting association, incorrect channel mapping, relay configuration mismatch, data interpretation problem.

Unit coverage: `backend/tests/test_consistency.py` (`test_51_disabled_with_pickup_and_trip_inconsistent`).

## Protection sequence check

Expected monotonic order when events are present:

`protection_pickup` → `protection_trip` → `breaker_trip_command` → `52a_change` → `current_interruption`

Fewer than two of these events → `UNVERIFIABLE`.

## Family checks

Aggregates assessments by function family (distance 21, directional 67/67N, earth fault 50N/51N/67N, overcurrent **50/51**, voltage 27/59, frequency 81U/81O/81R, differential 87T/87L/87B, breaker failure 50BF, auto-reclose 79, lockout 86, synchronism 25).

## Downstream effects

When `rca_must_remain_inconclusive` is true:

- RCA engine forces primary hypothesis to **INCONCLUSIVE** / UNKNOWN and blocks automatic RELAY_MISOPERATION confirmation path.
- Decision layer keeps event decision state **INCONCLUSIVE** until settings are verified.

## What consistency does *not* do

- It does not write settings to relays.
- It does not declare a definitive root cause.
- It does not treat `NOT_VERIFIED` settings as ground truth without labelling them.
