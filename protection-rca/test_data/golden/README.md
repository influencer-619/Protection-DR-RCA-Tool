# Golden datasets

Golden folders pin **expected** outcomes for regression testing against known COMTRADE fixtures and deterministic engine behaviour.

## Layout

```
test_data/golden/
  README.md                 # this file
  <CASE-ID>/
    expected.json           # machine-readable expectations
    notes.md                # optional human notes
```

Fixtures themselves live under `test_data/comtrade/` (do not duplicate large binary DAT files inside golden folders; reference them by relative path).

## Case ID convention

`EVT-SYNTH-<FAULT>-NNN` for synthetic cases, e.g. `EVT-SYNTH-AG-001`.

## expected.json schema (minimum)

| Field | Description |
|-------|-------------|
| `case_id` | Stable identifier |
| `fixture` | Relative paths to CFG/DAT (or CFF) |
| `comtrade` | Expected standard, revision, format, channels, samples |
| `support_status` | `SUPPORTED` / `PARTIALLY_SUPPORTED` / … — must match platform honesty |
| `fault` | Expected fault type / status when classifiable |
| `notes` | Limitations (never claim partial as fully validated) |

## Adding a case

1. Place or reuse a fixture under `test_data/comtrade/…`
2. Create `golden/<CASE-ID>/expected.json`
3. Add a pytest that loads expectations and asserts parse / classification / consistency
4. For IEEE 1991 or multi-rate fixtures, set `support_status` to `PARTIALLY_SUPPORTED`

## Current cases

| Case | Fixture | Intent |
|------|---------|--------|
| `EVT-SYNTH-AG-001` | `comtrade/ieee_1999/ag_fault.*` | IEEE 1999 ASCII AG fault, validated path |
