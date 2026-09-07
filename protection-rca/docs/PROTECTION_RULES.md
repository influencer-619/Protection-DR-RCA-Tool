# Protection rules

## Overview

The protection engine (`backend/protection/`) loads YAML rule packages from `rules/protection/` and assesses modular ANSI/IEC-style elements against:

- Timeline-derived observations (pickup / trip / reclose / lockout digitals)
- Settings resolved via the settings hierarchy (`settings/hierarchy/resolver.py`)
- Optional electrical context from signal processing

Outputs are `ProtectionAssessment` objects: enabled, pickup, trip, expected vs actual operation, timing, consistency flag, setting reference (source / version / group / verification), evidence IDs, confidence.

Rules version is tracked (`protection_rules_version` / `rules_version` on results).

## Elements implemented

| Code | Module | YAML | Description |
|------|--------|------|-------------|
| 21 | `el_21` | `element_21.yaml` | Distance |
| 50 | `el_50` | `element_50.yaml` | Instantaneous overcurrent |
| 51 | `el_51` | `element_51.yaml` | Time overcurrent |
| 50N | `el_50n` | `element_50n.yaml` | Instantaneous earth fault |
| 51N | `el_51n` | `element_51n.yaml` | Time earth fault |
| 67 | `el_67` | `element_67.yaml` | Directional overcurrent |
| 67N | `el_67n` | `element_67n.yaml` | Directional earth fault |
| 27 | `el_27` | `element_27.yaml` | Undervoltage |
| 59 | `el_59` | `element_59.yaml` | Overvoltage |
| 81U | `el_81u` | `element_81u.yaml` | Underfrequency |
| 81O | `el_81o` | `element_81o.yaml` | Overfrequency |
| 81R | `el_81r` | `element_81r.yaml` | Rate of change of frequency |
| 87T | `el_87t` | `element_87t.yaml` | Transformer differential |
| 87L | `el_87l` | `element_87l.yaml` | Line differential |
| 87B | `el_87b` | `element_87b.yaml` | Bus differential |
| 50BF | `el_50bf` | `element_50bf.yaml` | Breaker failure |
| 79 | `el_79` | `element_79.yaml` | Auto-reclose |
| 86 | `el_86` | `element_86.yaml` | Lockout |
| 25 | `el_25` | `element_25.yaml` | Synchronism check |

Dispatch map: `protection/elements/base_dispatch.py`.

## Channel → element matching

Digital channel names on the timeline are matched with regex preference for longer codes first (`50BF` before `50`, `51N` before `51`, etc.). Unmatched generic pickup/trip digitals are not assigned to an element.

## YAML rule shape (example: 51)

```yaml
rule_id: PROT-51-001
version: "1.0.0"
element: "51"
description: "Time overcurrent protection consistency and assessment rules"
inputs: [enabled, pickup, trip, pickup_time, trip_time]
logic:
  enabled_vs_pickup: true
  enabled_vs_trip: true
  pickup_vs_trip: true
  timing: true
expected_result: "Operate only when enabled and pickup criteria met"
severity:
  disabled_operation: HIGH
  trip_without_pickup: HIGH
  unverifiable_settings: MEDIUM
```

Element modules typically call shared assessment helpers with an electrical fault hint when available.

## Settings linkage

For each assessed element, the engine resolves parameters such as `enabled` through `resolve_setting(...)`, which always returns:

- `source` (hierarchy level or `NONE`)
- `version`, `group`
- `verification_status`: `VERIFIED` or `NOT_VERIFIED`
- candidates considered + explanation

Missing settings → assessment remains **unverifiable**; the platform does **not** invent values.

## Consistency hand-off

Protection assessments feed the consistency engine. Critical policy for disabled elements that still pickup/trip is documented in [CONSISTENCY_CHECKER.md](CONSISTENCY_CHECKER.md) (especially element **51**).

## Limitations

- Element logic is rule/assessment oriented; it is not a full vendor relay emulator.
- Without mapped digitals and settings, many elements report `UNVERIFIABLE`.
- If YAML rules are missing at the expected path, the engine records `Protection rules NOT AVAILABLE`.
