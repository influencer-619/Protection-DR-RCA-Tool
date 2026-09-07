# Engineering limitations

This platform is designed to **refuse false certainty**. The following behaviours are intentional.

## Vocabulary (do not reinterpret as success)

| Token | Meaning |
|-------|---------|
| `NOT CALCULABLE` / `NOT_CALCULABLE` | Quantity cannot be computed from available inputs (e.g. fault distance without line Z) |
| `NOT AVAILABLE` | Required artefact/service/setting absent |
| `NOT VERIFIED` / `NOT_VERIFIED` | Setting source not verified for the event |
| `INCONCLUSIVE` | Evidence insufficient or blocked by policy |
| `UNVERIFIABLE` | Consistency/protection check cannot be completed |
| `UNKNOWN` | Classification / hypothesis unresolved |
| `PARTIALLY_SUPPORTED` | Usable with documented limitations — **not fully validated** |
| `UNSUPPORTED` / `INVALID` | Must not be treated as validated analysis input |

Reports and templates must surface these tokens rather than inventing values.

## Explicit unsupported / partial cases

| Area | Limitation |
|------|------------|
| COMTRADE IEEE 1991 | **Partially supported** — reduced channel fields; not full validation claim |
| Multi-rate (`nrates > 1`) | **Partially supported** — flagged; not end-to-end validated |
| UTF-16 CFG | Unsupported |
| Unknown format/revision | Unsupported → decision may be `UNSUPPORTED_FORMAT` |
| Generative AI narratives | **Not used** — do not add LLM prose to “fill gaps” |
| OT control | **Not implemented** — no trip/close/write |
| Full vendor relay emulation | Not claimed; modular assessments only |
| ML anomaly / similarity | Default `NOT AVAILABLE` without approved model; cannot alone CONFIRM RCA |

## Fault distance

`fault_analysis` returns distance with `status: NOT_CALCULABLE` when line impedance / settings / apparent Z are missing or invalid, with an explicit reason string. Do not substitute a guessed km value.

## Settings

- Hierarchy never silently picks a source without recording it.
- Active / event-specific sources require verification flags; otherwise `NOT_VERIFIED`.
- Missing candidates → source `NONE`, version `NOT AVAILABLE`.

## Critical consistency → RCA

If **51** (or any element) is `enabled=false` but pickup/trip observed:

- Consistency: `INCONSISTENT` + investigation hints  
- RCA: **forced INCONCLUSIVE**  
- **Forbidden:** auto-conclusion “relay malfunction”

## Breaker assessment

Without sufficient timing evidence, breaker assessment remains `INCONCLUSIVE` rather than NORMAL/FAILED.

## What engineers must still do

- Verify active setting group and file–event association  
- Confirm channel mapping  
- Treat partial COMTRADE support as provisional  
- Complete field investigation when decision state is `ENGINEER_REVIEW_REQUIRED` or `REQUEST_FIELD_INVESTIGATION`

## Non-goals checklist

- [ ] No silent CFG/DAT repair  
- [ ] No claiming unsupported formats as validated  
- [ ] No generative root-cause storytelling  
- [ ] No OT actuation through this API  
