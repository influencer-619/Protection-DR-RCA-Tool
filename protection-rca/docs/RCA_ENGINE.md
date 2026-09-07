# RCA engine

## Design

The RCA engine (`backend/rca/`) is a **deterministic, evidence-gated hypothesis scorer**. It does not use generative AI.

- Hypothesis definitions: `rules/rca/hypotheses.yaml`
- Engine: `HypothesisEngine`
- Decision aggregation: `backend/decision/`

## Scoring weights (default)

| Signal | Weight |
|--------|--------|
| Deterministic evidence | 0.50 |
| Consistency | 0.20 |
| Electrical | 0.15 |
| ML (optional, supporting only) | 0.10 |
| Similarity (optional, supporting only) | 0.05 |

Weights are normalized. When ML/similarity are unavailable, their contributions are zero and those modules report `NOT AVAILABLE`.

**ML alone cannot produce CONFIRMED.** If deterministic score is low, CONFIRMED is demoted to PROBABLE.

## Hypothesis statuses

`CONFIRMED` · `PROBABLE` · `POSSIBLE` · `UNLIKELY` · `INCONCLUSIVE`

`CONFIRMED` requires all `required_for_confirmed` evidence keys present, strong deterministic score, and adequate consistency score.

## Catalogue (ids)

From `hypotheses.yaml`:

- `EXTERNAL_LINE_FAULT`, `INTERNAL_FEEDER_FAULT`, `CABLE_FAULT`, `TRANSFORMER_INTERNAL_FAULT`
- `LIGHTNING`, `VEGETATION`, `INSULATION_FLASHOVER`
- `CT_SATURATION`, `VT_CVT_ABNORMALITY`
- `PROTECTION_SETTING_ERROR`, `RELAY_CONFIGURATION_ERROR`, `RELAY_MISOPERATION`
- `BREAKER_FAILURE`, `COMMUNICATION_FAILURE`, `INTERTRIP_OPERATION`
- `SWITCHING_TRANSIENT`, `EXTERNAL_GRID_DISTURBANCE`
- `UNKNOWN`

Each id lists evidence keys required for CONFIRMED (e.g. `RELAY_MISOPERATION` requires `settings_verified`, `electrical_no_fault`, `trip_observed`).

## Critical consistency override

If consistency reports `rca_must_remain_inconclusive` (classic case: **51 enabled=false** with pickup/trip):

1. `forced_inconclusive = True`
2. Limitation text: investigate settings; do **not** auto-conclude relay malfunction
3. `RELAY_MISOPERATION` forced to `INCONCLUSIVE` with missing `active_setting_verification`
4. Primary result becomes `UNKNOWN` / `INCONCLUSIVE` with contradicting evidence `critical_setting_inconsistency`

## Decision states

`backend/decision/` maps pipeline outcomes to event-level states including:

- `ANALYSIS_COMPLETE` / `ANALYSIS_COMPLETE_WITH_WARNINGS`
- `INCONCLUSIVE`
- `DATA_INSUFFICIENT`
- `UNSUPPORTED_FORMAT`
- `ENGINEER_REVIEW_REQUIRED`

## Reporting

Sentence templates under `templates/sentences/rca.yaml` and HTML Jinja under `templates/reports/` render deterministic text. Missing fields surface as `[… NOT AVAILABLE]` rather than invented prose.

## Non-claims

- RCA does not issue control actions.
- Absence of evidence is not evidence of absence without stating `INCONCLUSIVE` / missing evidence lists.
- Statistical models, when present, are advisory only.
