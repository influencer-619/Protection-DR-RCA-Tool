"""Generate protection element modules and YAML rules."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ELEM_DIR = ROOT / "backend" / "protection" / "elements"
RULES_PROT = ROOT / "rules" / "protection"
RULES_CONS = ROOT / "rules" / "consistency"
RULES_RCA = ROOT / "rules" / "rca"
RULES_FAULT = ROOT / "rules" / "fault_classification"
SENT = ROOT / "templates" / "sentences"

for d in (ELEM_DIR, RULES_PROT, RULES_CONS, RULES_RCA, RULES_FAULT, SENT):
    d.mkdir(parents=True, exist_ok=True)

ELEMENTS = [
    ("21", "Distance"),
    ("50", "Instantaneous overcurrent"),
    ("51", "Time overcurrent"),
    ("50N", "Instantaneous earth fault"),
    ("51N", "Time earth fault"),
    ("67", "Directional overcurrent"),
    ("67N", "Directional earth fault"),
    ("27", "Undervoltage"),
    ("59", "Overvoltage"),
    ("81U", "Underfrequency"),
    ("81O", "Overfrequency"),
    ("81R", "ROCOF"),
    ("87T", "Transformer differential"),
    ("87L", "Line differential"),
    ("87B", "Bus differential"),
    ("50BF", "Breaker failure"),
    ("79", "Auto-reclose"),
    ("86", "Lockout"),
    ("25", "Synchronism check"),
]

YAML_REQUIRED = {"21", "50", "51", "50N", "51N", "67", "27", "59", "81U", "87T", "50BF", "79", "86"}


def mod_name(code: str) -> str:
    return "el_" + code.lower()


for code, desc in ELEMENTS:
    class_name = "Element_" + code
    content = f'''"""Protection element {code} — {desc}."""

from __future__ import annotations

from protection.models import ElementContext, ProtectionAssessment, ProtectionElement, base_assess


class {class_name}(ProtectionElement):
    element_code = "{code}"

    def assess(self, ctx: ElementContext) -> ProtectionAssessment:
        fault_hint = bool(ctx.electrical.get("fault_indicated", False))
        result = base_assess("{code}", ctx, electrical_fault_hint=fault_hint)
        result.metadata["description"] = "{desc}"
        return result


ELEMENT = {class_name}()
'''
    (ELEM_DIR / f"{mod_name(code)}.py").write_text(content, encoding="utf-8")

registry_lines = "\n".join(f'    "{c}": "{mod_name(c)}",' for c, _ in ELEMENTS)
(ELEM_DIR / "base_dispatch.py").write_text(
    f'''"""Registry of protection element modules."""

from __future__ import annotations

from importlib import import_module
from typing import Dict

from protection.models import ProtectionElement

_MODULE_BY_CODE = {{
{registry_lines}
}}

ELEMENT_REGISTRY: Dict[str, ProtectionElement] = {{}}


def _load() -> None:
    if ELEMENT_REGISTRY:
        return
    for code, name in _MODULE_BY_CODE.items():
        mod = import_module(f"protection.elements.{{name}}")
        ELEMENT_REGISTRY[code] = mod.ELEMENT


def get_element(code: str) -> ProtectionElement | None:
    _load()
    return ELEMENT_REGISTRY.get(code)


def all_elements() -> Dict[str, ProtectionElement]:
    _load()
    return dict(ELEMENT_REGISTRY)
''',
    encoding="utf-8",
)

# Protection YAML
for code, desc in ELEMENTS:
    if code not in YAML_REQUIRED and code not in {"67N", "81O", "81R", "87L", "87B", "25"}:
        # still write required set primarily; write all for completeness of engine
        pass
    yaml = f'''rule_id: PROT-{code}-001
version: "1.0.0"
element: "{code}"
description: "{desc} protection consistency and assessment rules"
inputs:
  - enabled
  - pickup
  - trip
  - pickup_time
  - trip_time
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
effective_date: "2026-01-01"
'''
    (RULES_PROT / f"element_{code.lower()}.yaml").write_text(yaml, encoding="utf-8")

(RULES_CONS / "core_checks.yaml").write_text(
    '''version: "1.0.0"
rules:
  - rule_id: CONS-ENABLED-PICKUP
    check_type: enabled_vs_pickup
    description: "Enabled=FALSE with pickup=TRUE is INCONSISTENT"
    severity: HIGH
  - rule_id: CONS-ENABLED-TRIP
    check_type: enabled_vs_trip
    description: "Enabled=FALSE with trip=TRUE is INCONSISTENT"
    severity: CRITICAL
  - rule_id: CONS-PICKUP-TRIP
    check_type: pickup_vs_trip
    description: "Trip without pickup requires investigation"
    severity: HIGH
  - rule_id: CONS-SEQUENCE
    check_type: protection_sequence
    description: "Pickup -> Trip -> Breaker -> Current interruption"
    severity: MEDIUM
  - rule_id: CONS-DISTANCE
    check_type: distance
    elements: ["21"]
    severity: MEDIUM
  - rule_id: CONS-DIRECTIONAL
    check_type: directional
    elements: ["67", "67N"]
    severity: MEDIUM
  - rule_id: CONS-EARTH
    check_type: earth_fault
    elements: ["50N", "51N", "67N"]
    severity: MEDIUM
  - rule_id: CONS-OC
    check_type: overcurrent
    elements: ["50", "51"]
    severity: MEDIUM
  - rule_id: CONS-VOLTAGE
    check_type: voltage
    elements: ["27", "59"]
    severity: MEDIUM
  - rule_id: CONS-FREQ
    check_type: frequency
    elements: ["81U", "81O", "81R"]
    severity: MEDIUM
  - rule_id: CONS-DIFF
    check_type: differential
    elements: ["87T", "87L", "87B"]
    severity: MEDIUM
  - rule_id: CONS-BF
    check_type: breaker_failure
    elements: ["50BF"]
    severity: HIGH
  - rule_id: CONS-AR
    check_type: auto_reclose
    elements: ["79"]
    severity: MEDIUM
  - rule_id: CONS-LOCKOUT
    check_type: lockout
    elements: ["86"]
    severity: HIGH
  - rule_id: CONS-SYNC
    check_type: synchronism
    elements: ["25"]
    severity: LOW
critical_rule:
  id: CONS-CRITICAL-51-DISABLED-OPERATE
  description: >
    If 51 enabled=FALSE but pickup/trip TRUE, mark INCONSISTENT,
    investigate setting sources, RCA remains INCONCLUSIVE until verified.
    Do NOT auto-conclude relay malfunction.
''',
    encoding="utf-8",
)

(RULES_RCA / "hypotheses.yaml").write_text(
    '''version: "1.0.0"
scoring_weights:
  deterministic: 0.50
  consistency: 0.20
  electrical: 0.15
  ml: 0.10
  similarity: 0.05
hypotheses:
  - id: EXTERNAL_LINE_FAULT
    required_for_confirmed:
      - fault_classified
      - protection_operated
      - current_increase_observed
  - id: INTERNAL_FEEDER_FAULT
    required_for_confirmed:
      - fault_classified
      - protection_operated
  - id: CABLE_FAULT
    required_for_confirmed:
      - fault_classified
      - cable_asset_confirmed
  - id: TRANSFORMER_INTERNAL_FAULT
    required_for_confirmed:
      - differential_operated
      - through_fault_excluded
  - id: LIGHTNING
    required_for_confirmed:
      - lightning_evidence
  - id: VEGETATION
    required_for_confirmed:
      - field_report_vegetation
  - id: INSULATION_FLASHOVER
    required_for_confirmed:
      - insulation_evidence
  - id: CT_SATURATION
    required_for_confirmed:
      - waveform_distortion
      - harmonic_evidence
  - id: VT_CVT_ABNORMALITY
    required_for_confirmed:
      - voltage_channel_anomaly
  - id: PROTECTION_SETTING_ERROR
    required_for_confirmed:
      - setting_verified
      - inconsistency_with_verified_settings
  - id: RELAY_CONFIGURATION_ERROR
    required_for_confirmed:
      - configuration_verified
      - mismatch_documented
  - id: RELAY_MISOPERATION
    required_for_confirmed:
      - settings_verified
      - electrical_no_fault
      - trip_observed
  - id: BREAKER_FAILURE
    required_for_confirmed:
      - trip_command_observed
      - current_persists
      - bf_logic_satisfied
  - id: COMMUNICATION_FAILURE
    required_for_confirmed:
      - comm_channel_evidence
  - id: INTERTRIP_OPERATION
    required_for_confirmed:
      - intertrip_signal_observed
  - id: SWITCHING_TRANSIENT
    required_for_confirmed:
      - switching_event_correlated
  - id: EXTERNAL_GRID_DISTURBANCE
    required_for_confirmed:
      - external_event_correlated
  - id: UNKNOWN
    required_for_confirmed: []
''',
    encoding="utf-8",
)

(RULES_FAULT / "classification.yaml").write_text(
    '''version: "1.0.0"
types: [AG, BG, CG, AB, BC, CA, ABG, BCG, CAG, ABC, ABCG, UNKNOWN]
thresholds:
  phase_current_ratio: 2.0
  voltage_collapse_ratio: 0.8
  zero_sequence_ratio: 0.2
  negative_sequence_ratio: 0.2
rules:
  - id: FC-AG
    type: AG
    require:
      - Ia_elevated
      - Ib_not_elevated
      - Ic_not_elevated
      - V0_or_I0_present
  - id: FC-BG
    type: BG
    require:
      - Ib_elevated
      - Ia_not_elevated
      - Ic_not_elevated
      - V0_or_I0_present
  - id: FC-CG
    type: CG
    require:
      - Ic_elevated
      - Ia_not_elevated
      - Ib_not_elevated
      - V0_or_I0_present
  - id: FC-AB
    type: AB
    require:
      - Ia_elevated
      - Ib_elevated
      - Ic_not_elevated
      - ground_absent
  - id: FC-BC
    type: BC
    require:
      - Ib_elevated
      - Ic_elevated
      - Ia_not_elevated
      - ground_absent
  - id: FC-CA
    type: CA
    require:
      - Ic_elevated
      - Ia_elevated
      - Ib_not_elevated
      - ground_absent
  - id: FC-ABG
    type: ABG
    require:
      - Ia_elevated
      - Ib_elevated
      - Ic_not_elevated
      - V0_or_I0_present
  - id: FC-BCG
    type: BCG
    require:
      - Ib_elevated
      - Ic_elevated
      - Ia_not_elevated
      - V0_or_I0_present
  - id: FC-CAG
    type: CAG
    require:
      - Ic_elevated
      - Ia_elevated
      - Ib_not_elevated
      - V0_or_I0_present
  - id: FC-ABC
    type: ABC
    require:
      - Ia_elevated
      - Ib_elevated
      - Ic_elevated
      - ground_absent
  - id: FC-ABCG
    type: ABCG
    require:
      - Ia_elevated
      - Ib_elevated
      - Ic_elevated
      - V0_or_I0_present
''',
    encoding="utf-8",
)

for name, body in {
    "protection.yaml": '''sentences:
  operated_consistent: "Protection element {element} operated consistently with the configured protection parameters."
  operated_inconsistent: "Protection element {element} operation is inconsistent with the configured enabled state."
  not_operated: "Protection element {element} did not operate during the disturbance record window."
  unverifiable: "Protection element {element} assessment is UNVERIFIABLE due to insufficient setting or channel evidence."
''',
    "consistency.yaml": '''sentences:
  inconsistent_disabled: "The available records contain an inconsistency between the configured protection state and the observed relay operation. The active setting group at the event time could not be independently verified."
  consistent: "Observed protection behavior is consistent with the resolved settings for element {element}."
  data_quality: "A data quality issue prevents reliable consistency assessment for element {element}."
''',
    "fault.yaml": '''sentences:
  classified: "The disturbance record indicates a {fault_type} fault."
  probable: "The disturbance record indicates a probable {fault_type} fault."
  inconclusive: "Fault type could not be conclusively determined from available electrical evidence."
  distance_not_calculable: "FAULT DISTANCE: NOT CALCULABLE. REASON: Required line/settings data unavailable."
''',
    "rca.yaml": '''sentences:
  confirmed: "Hypothesis {hypothesis} is CONFIRMED based on satisfied evidence requirements."
  probable: "Hypothesis {hypothesis} is PROBABLE based on supporting engineering evidence."
  possible: "Hypothesis {hypothesis} remains POSSIBLE; required confirming evidence is incomplete."
  unlikely: "Hypothesis {hypothesis} is UNLIKELY given contradicting evidence."
  inconclusive: "Root cause assessment is INCONCLUSIVE pending verification of settings or additional evidence."
''',
}.items():
    (SENT / name).write_text(body, encoding="utf-8")

print("OK", len(ELEMENTS), "elements + rules")
