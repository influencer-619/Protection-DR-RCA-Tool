/** Human labels for RCA evidence tokens (avoid raw snake_case in UI). */

const EVIDENCE_LABELS: Record<string, string> = {
  fault_classified: 'Fault type classified from electrical evidence',
  fault_classified_strong: 'Strong / high-confidence fault classification',
  current_increase_observed: 'Fault current increase observed',
  protection_operated: 'Protection trip/operate observed on DR (targets / digitals)',
  protection_operated_consistently:
    'Protection operate also consistent with verified settings (bonus)',
  protection_responded: 'Protection pickup or trip asserted',
  trip_observed: 'Trip asserted',
  element_behavior_consistent: 'Element behavior marked consistent',
  settings_behavior_consistent: 'Settings vs behavior consistent',
  distance_element_operated: 'Distance element (21) operated',
  line_diff_operated: 'Line differential (87L) operated',
  distance_estimate_available: 'Fault location estimate available',
  loop_impedance_available: 'Loop impedance available',
  lightning_evidence: 'Lightning / storm strike evidence',
  field_report_vegetation: 'Vegetation / tree contact (field report)',
  insulation_evidence: 'Insulation flashover evidence',
  cable_asset_confirmed: 'Cable / underground asset confirmed',
  switching_event_correlated: 'Switching event correlated',
  external_event_correlated: 'External grid event correlated',
  comm_channel_evidence: 'Pilot / carrier / COMM channel evidence',
  intertrip_signal_observed: 'Intertrip / transfer-trip observed',
  scheme_zone_mismatch: 'Hypothesis does not match operated protection zone',
  cause_specific_evidence_absent: 'Cause-specific field evidence not yet provided',
  scheme_library_matched: 'Protection scheme profile matched',
  scheme_pilot: 'Pilot / teleprotection scheme context',
  overcurrent_element_operated: 'Overcurrent element operated',
  earth_fault_element_operated: 'Earth-fault element operated',
  transformer_diff_operated: 'Transformer differential operated',
  bus_diff_operated: 'Bus differential operated',
  generator_diff_operated: 'Generator differential operated',
  bf_logic_satisfied: 'Breaker-failure logic satisfied',
  differential_operated: 'Differential element operated',
  through_fault_excluded:
    'Through-fault excluded (Id/Ir operate above restraint characteristic)',
};

export function humanizeEvidenceToken(token: string): string {
  if (!token) return '—';
  if (EVIDENCE_LABELS[token]) return EVIDENCE_LABELS[token];
  if (token.startsWith('scheme_profile_')) {
    return `Scheme profile: ${token.replace('scheme_profile_', '').replace(/_/g, ' ')}`;
  }
  if (token.startsWith('scheme_id_')) {
    return `Matched scheme: ${token.replace('scheme_id_', '').replace(/_/g, ' ')}`;
  }
  return token.replace(/_/g, ' ');
}
