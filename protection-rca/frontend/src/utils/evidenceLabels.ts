/** Human labels for RCA evidence tokens (avoid raw snake_case in UI). */

const EVIDENCE_LABELS: Record<string, string> = {
  fault_classified: 'Fault type classified from electrical evidence',
  fault_classified_strong: 'Strong / high-confidence fault classification',
  current_increase_observed: 'Fault current increase observed',
  protection_operated: 'Protection trip asserted',
  protection_operated_consistently:
    'Protection operate also consistent with verified settings (bonus)',
  protection_responded: 'Protection response asserted',
  protection_pickup_asserted: 'Protection pickup asserted',
  protection_trip_asserted: 'Protection trip asserted',
  protection_pickup_with_trip: 'Protection pickup with trip',
  trip_observed: 'Trip asserted',
  element_behavior_consistent: 'Element behaviour marked consistent',
  settings_behavior_consistent: 'Settings vs behaviour consistent',
  distance_element_operated: 'Distance element (21) operated',
  distance_estimate_available: 'Fault location estimate available',
  loop_impedance_available: 'Loop impedance available',
  ground_involved: 'Ground / earth involved in the fault',
  lightning_evidence: 'Lightning / storm strike evidence',
  field_report_vegetation: 'Vegetation / tree contact (field report)',
  insulation_evidence: 'Insulation flashover evidence',
  cable_asset_confirmed: 'Cable / underground asset confirmed',
  switching_event_correlated: 'Switching event correlated',
  external_event_correlated: 'External grid event correlated',
  comm_channel_evidence: 'Pilot / carrier / COMM channel evidence',
  intertrip_signal_observed: 'Intertrip / transfer-trip observed',
  cascade_lbb_detected: 'LBB / multi-bay cascade (initiator BF → upstream clearance)',
  cascade_upstream_clearance: 'Upstream / backup bay cleared via intertrip',
  bf_logic_satisfied: 'Breaker-failure (50BF / LBB) logic satisfied',
  scheme_zone_mismatch: 'Hypothesis does not match operated protection zone',
  cause_specific_evidence_absent: 'Cause-specific field evidence not yet provided',
  scheme_library_matched: 'Protection scheme profile matched',
  scheme_pilot: 'Pilot / teleprotection scheme context',
  scheme_distance: 'Distance protection scheme context',
  scheme_distance_present: 'Distance protection present in scheme',
  scheme_distance_profile: 'Distance scheme profile matched',
  scheme_overcurrent_present: 'Overcurrent protection present in scheme',
  overcurrent_element_operated: 'Overcurrent element (50/51) trip asserted',
  overcurrent_element_picked_up: 'Overcurrent element (50/51) pickup asserted (no trip)',
  earth_fault_element_operated: 'Earth-fault element (50N/51N/67N) trip asserted',
  earth_fault_element_picked_up:
    'Earth-fault element (50N/51N/67N) pickup asserted (no trip)',
  directional_element_operated: 'Directional element (67) trip asserted',
  directional_element_picked_up: 'Directional element (67) pickup asserted (no trip)',
  transformer_diff_operated: 'Transformer differential trip asserted',
  transformer_diff_picked_up: 'Transformer differential pickup asserted',
  bus_diff_operated: 'Bus differential trip asserted',
  bus_diff_picked_up: 'Bus differential pickup asserted',
  generator_diff_operated: 'Generator differential trip asserted',
  generator_diff_picked_up: 'Generator differential pickup asserted',
  line_diff_operated: 'Line differential trip asserted',
  line_diff_picked_up: 'Line differential pickup asserted',
  differential_operated: 'Differential element trip asserted',
  magnetizing_inrush_possible: 'Magnetizing inrush / charging signature (H2)',
  motor_start_possible: 'Motor start / starting-current signature',
  motor_protection_present: 'Motor-protection digitals present (start/thermal/stall)',
  motor_element_operated: 'Motor element (46/48/49) trip asserted',
  motor_element_picked_up: 'Motor element (46/48/49) pickup asserted (no trip)',
  scheme_motor: 'Motor protection scheme context',
  through_fault_excluded:
    'Through-fault excluded (Id/Ir operate above restraint characteristic)',
  ct_saturation: 'CT saturation indicated',
  ct_saturation_possible: 'Possible CT saturation',
  electrical_no_fault: 'Electrical evidence indicates non-fault event',
  dfr_non_fault_event:
    'DFR classed as non-fault (energization / motor / switching / disturbance)',
  event_class_FAULT: 'DFR event class: FAULT',
  event_class_ENERGIZATION: 'DFR event class: ENERGIZATION (inrush / charging)',
  event_class_MOTOR_START: 'DFR event class: MOTOR_START',
  event_class_SWITCHING: 'DFR event class: SWITCHING',
  event_class_DISTURBANCE: 'DFR event class: DISTURBANCE',
  event_class_UNKNOWN: 'DFR event class: UNKNOWN',
  switch_onto_fault_possible: 'Switch-onto-fault pattern possible',
  switch_onto_fault_context: 'Close / energize into fault context',
  sotf_element_asserted: 'SOTF digital / element asserted',
  breaker_close_observed: 'Pre-trip breaker close observed',
  autoreclose_issued: 'Autoreclose issued (not SOTF close)',
};

const EVENT_CLASS_LABELS: Record<string, string> = {
  FAULT: 'Fault',
  ENERGIZATION: 'Energization / inrush',
  MOTOR_START: 'Motor start',
  SWITCHING: 'Switching',
  DISTURBANCE: 'Disturbance',
  UNKNOWN: 'Unknown',
};

/** Extract IEEE/PSRC DFR event class from persisted fault features or live analysis. */
export function eventClassFromFault(
  fault?: { event_class?: string | null; features?: Record<string, unknown> | null; evidence?: Record<string, unknown> | null } | null,
): string | null {
  if (!fault) return null;
  if (typeof fault.event_class === 'string' && fault.event_class) return fault.event_class;
  const feat = fault.features;
  if (feat && typeof feat.event_class === 'string' && feat.event_class) return feat.event_class;
  const evc = feat?.event_classification ?? fault.evidence?.event_classification;
  if (evc && typeof evc === 'object' && evc !== null) {
    const ec = (evc as { event_class?: unknown }).event_class;
    if (typeof ec === 'string' && ec) return ec;
  }
  return null;
}

export function humanizeEventClass(ec: string | null | undefined): string {
  if (!ec) return '—';
  return EVENT_CLASS_LABELS[ec] || ec.replace(/_/g, ' ');
}

/** Shunt-fault attributes (ground / AG phases) only apply when DFR class is FAULT. */
export function isShuntFaultEventClass(ec: string | null | undefined): boolean {
  return String(ec || '').toUpperCase() === 'FAULT';
}

/** Known non-fault DFR classes (not UNKNOWN). */
export function isKnownNonFaultEventClass(ec: string | null | undefined): boolean {
  const u = String(ec || '').toUpperCase();
  return (
    u === 'ENERGIZATION' ||
    u === 'MOTOR_START' ||
    u === 'SWITCHING' ||
    u === 'DISTURBANCE'
  );
}

export function groundInvolvedLabel(
  ec: string | null | undefined,
  groundInvolved: boolean | null | undefined,
): string {
  if (isKnownNonFaultEventClass(ec)) return 'N/A (non-fault event)';
  if (!isShuntFaultEventClass(ec)) return '—';
  if (groundInvolved == null) return '—';
  return groundInvolved ? 'Yes' : 'No';
}

/**
 * Display label for fault type KPI / tables.
 * Avoid bare "UNKNOWN" — use PSRC-style technical wording.
 */
export function humanizeFaultType(
  faultType: string | null | undefined,
  eventClass?: string | null,
): string {
  const ft = String(faultType || '').trim().toUpperCase();
  const ec = String(eventClass || '').trim().toUpperCase();

  if (!ft || ft === '—' || ft === '-') {
    if (isKnownNonFaultEventClass(ec)) return 'N/A — non-fault event';
    return '—';
  }

  // Non-fault DFR class: AG/AB/… type is not published
  if (isKnownNonFaultEventClass(ec) && (ft === 'UNKNOWN' || ft === 'INCONCLUSIVE')) {
    return 'N/A — non-fault event';
  }

  if (ft === 'UNKNOWN' || ft === 'INCONCLUSIVE') {
    if (ec === 'FAULT') return 'Unclassified (type indeterminate)';
    if (ec === 'UNKNOWN' || !ec) return 'Unclassified';
    return 'Unclassified';
  }

  // Keep ANSI phase codes as-is (AG, AB, ABCG, …)
  return String(faultType).trim();
}

export function humanizeEvidenceToken(token: string): string {
  const t = (token || '').trim();
  if (!t || t === '—' || t === '-') return '—';
  if (EVIDENCE_LABELS[t]) return EVIDENCE_LABELS[t];
  if (t.startsWith('event_class_')) {
    return `DFR event class: ${t.replace('event_class_', '').replace(/_/g, ' ')}`;
  }
  if (t.startsWith('scheme_profile_')) {
    return `Scheme profile: ${t.replace('scheme_profile_', '').replace(/_/g, ' ')}`;
  }
  if (t.startsWith('scheme_id_')) {
    return `Matched scheme: ${t.replace('scheme_id_', '').replace(/_/g, ' ')}`;
  }
  if (t.startsWith('scheme_')) {
    return `Scheme: ${t.replace(/^scheme_/, '').replace(/_/g, ' ')}`;
  }
  // Already a sentence (contains spaces and lowercase words)
  if (/\s/.test(t) && /[a-z]/.test(t)) return t;
  return t.replace(/_/g, ' ');
}

/** Humanize one note or a `;`-separated list of tokens / notes. */
export function humanizeEvidenceNotes(raw: string | null | undefined): string {
  if (!raw || !raw.trim()) return '—';
  return raw
    .split(';')
    .map((part) => humanizeEvidenceToken(part.trim()))
    .filter((p) => p && p !== '—')
    .join(' · ');
}

export function formatConfidencePct(confidence: number | null | undefined): string {
  if (confidence == null || !Number.isFinite(confidence)) return '—';
  return `${Math.round(confidence * 100)}%`;
}
