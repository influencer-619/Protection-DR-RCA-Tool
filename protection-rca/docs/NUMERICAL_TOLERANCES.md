# Numerical tolerances

Configured in application settings (`backend/app/core/config.py`, overridable via environment / `.env.example`).

## Defaults

| Parameter | Env var | Default | Interpretation |
|-----------|---------|---------|----------------|
| Nominal system frequency | `DEFAULT_NOMINAL_FREQUENCY` | `50.0` Hz | Default when CFG frequency absent / for analysis context |
| Phasor magnitude | `PHASOR_MAGNITUDE_TOLERANCE` | `0.02` (2%) | Relative magnitude comparison band |
| Phase angle | `PHASE_ANGLE_TOLERANCE_DEG` | `1.0` ° | Absolute angle tolerance |
| Frequency | `FREQUENCY_TOLERANCE_HZ` | `0.05` Hz | Frequency estimate agreement |
| RMS | `RMS_TOLERANCE` | `0.02` (2%) | Relative RMS comparison |
| Impedance | `IMPEDANCE_TOLERANCE` | `0.05` (5%) | Relative impedance magnitude band |
| Timestamp | `TIMESTAMP_TOLERANCE_US` | `10` µs | Configured platform timestamp slack |

## Related hard-coded / module behaviour

| Check | Behaviour |
|-------|-----------|
| COMTRADE nominal frequency validation | Warning if outside **15–70 Hz** |
| Timestamp engine spacing | Assesses monotonicity / duplicates; spacing checks use an internal microsecond tolerance (see `comtrade/timestamps.py`) |
| Consistency sequence ordering | Times compared with `1e-9` s epsilon for monotonicity |
| Scaling | `a * raw + b` with optional P/S ratio; zero secondary → validation error |

## Fault classification thresholds (rules)

From `rules/fault_classification/classification.yaml` (rule thresholds, not the config tolerances above):

| Threshold key | Default |
|---------------|---------|
| `phase_current_ratio` | 2.0 |
| `voltage_collapse_ratio` | 0.8 |
| `zero_sequence_ratio` | 0.2 |
| `negative_sequence_ratio` | 0.2 |

## Guidance

1. Document any production override of tolerances in the analysis job `component_versions` / report limitations.  
2. Do not tighten tolerances to “force” a CONFIRMED RCA when evidence is missing — prefer `INCONCLUSIVE`.  
3. When a quantity cannot meet calculability requirements, emit `NOT_CALCULABLE` instead of comparing within tolerance.  
4. IEEE 1991 / multi-rate partial records may carry larger practical uncertainty than these numeric bands imply — state partial support explicitly.
