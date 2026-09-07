# COMTRADE support matrix

This document reflects **actual detector/parser/validator behaviour** in `backend/comtrade/`.  
Do **not** treat partially supported or unsupported cases as fully validated.

Support vocabulary (`SupportStatus` / `ValidationStatus`):

| Status | Meaning |
|--------|---------|
| `SUPPORTED` / `VALID` | Detected revision + format handled; validation passed without partial markers |
| `VALID_WITH_WARNINGS` | Usable; non-fatal warnings |
| `PARTIALLY_SUPPORTED` | Parsed with known limitations (e.g. IEEE 1991, multi-rate) |
| `UNSUPPORTED` / `INVALID` | Not accepted as a validated analysis input |
| `NOT_VALIDATED` | Validation did not run |

The validator **never silently repairs** records.

---

## Validated (primary support)

Intended full path for production-like analysis:

| Dimension | Supported values |
|-----------|------------------|
| Standards | IEEE C37.111 / IEC 60255-24 dual-logo where applicable |
| Revisions | **IEEE 1999**, **IEEE 2013**, **IEC 2001**, **IEC 2013** |
| Containers | `CFG` + `DAT`, `CFF` (unpacked sections) |
| Data formats | `ASCII`, `BINARY`, `BINARY32`, `FLOAT32` |
| Sampling | Single rate section (`nrates == 1`) |
| Encoding | UTF-8 / ASCII CFG (lossy read with encoding detection) |

Reference fixture: `test_data/comtrade/ieee_1999/ag_fault.cfg` + `.dat`  
Golden case: `test_data/golden/EVT-SYNTH-AG-001/`.

Parser registry maps:

| (standard, revision) | Parser class |
|----------------------|--------------|
| IEEE 1999 | `Ieee1999Parser` |
| IEEE 2013 | `Ieee2013Parser` |
| IEC 2001 | `Iec2001Parser` |
| IEC 2013 | `Iec2013Parser` |
| IEC 1999 → IEC 2001 | alias |
| IEEE 2001 → IEEE 1999 | alias |

---

## Partially supported

These are **parsed and flagged**; analysis may proceed with limitations recorded. They are **not** claimed as fully validated.

### IEEE C37.111-1991

- Detector returns `PARTIALLY_SUPPORTED` when revision is `1991`.
- Parser: `Ieee1991Parser` — ASCII/BINARY CFG/DAT without primary/secondary/PS fields on analog lines.
- Reduced channel-field fidelity vs 1999+.
- Validation may yield `PARTIALLY_SUPPORTED` when partial/unsupported feature markers are present.

### Multi-rate sampling (`nrates > 1`)

- Detector appends unsupported/partial note: *Multiple sample-rate sections (nrates > 1)*.
- Validator emits warning code `MULTI_RATE` (“partially supported”).
- Overall detection/validation status → `PARTIALLY_SUPPORTED`.
- Downstream signal processing assumes a primary rate section; multi-rate fidelity is **not** validated end-to-end.

### Other partial markers

- Features listed on `record.unsupported_features` surface as `UNSUPPORTED_FEATURE` warnings and drive `PARTIALLY_SUPPORTED`.
- CFF with embedded binary DAT is unpacked via `CffParser` (operational path exists; treat exotic CFF layouts cautiously and check validation status).

---

## Unsupported / not validated

| Case | Behaviour |
|------|-----------|
| Unknown revision / container / data format | Detection `UNSUPPORTED` |
| Non-COMTRADE inputs | `is_comtrade=false`, `UNSUPPORTED` |
| UTF-16 encoded CFG | Documented as unsupported in detector feature map |
| Silent CFG/DAT repair | **Never performed** — invalid structures fail validation |
| Claiming 1991 or multi-rate as “validated production” | **Forbidden** in engineering reports |

When format is unsupported, decision layer can set decision state `UNSUPPORTED_FORMAT` / data insufficient paths.

---

## Validation checks (summary)

`ComtradeValidator` checks identity, channels, sample counts, raw/scaled lengths, sample rates, start/trigger times, timestamp monotonicity, nominal frequency band (15–70 Hz), and source file presence. Errors → `INVALID`; partial codes → `PARTIALLY_SUPPORTED`; warnings only → `VALID_WITH_WARNINGS`.

---

## Engineering rule

> Never claim an unsupported or partially supported COMTRADE variant as **validated**.  
> Record `validation_status`, `data_quality`, and limitations on the event / report.
