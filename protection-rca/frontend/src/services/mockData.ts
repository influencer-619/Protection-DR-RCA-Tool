import type {
  AnalysisJob,
  Asset,
  AuditLogEntry,
  Bay,
  Breaker,
  ComtradeFile,
  ConsistencyFinding,
  DashboardStats,
  EvidenceItem,
  Event,
  EventFile,
  FaultClassification,
  Measurement,
  ModelVersion,
  ProtectionOperation,
  RcaHypothesis,
  Relay,
  Report,
  RuleVersion,
  SettingGroup,
  SettingSourceInfo,
  SettingVersion,
  Substation,
  TimelineEntry,
  User,
  WaveformChannelData,
  WaveformMarker,
} from '@/types';

export const DEMO_USER: User = {
  id: 'u-001',
  username: 's.engineer',
  email: 's.engineer@utility.local',
  full_name: 'S. Protection Engineer',
  role: 'PROTECTION_ENGINEER',
  is_active: true,
  last_login_at: '2026-09-04T06:00:00Z',
};

export const DEMO_STATS: DashboardStats = {
  total_events: 148,
  awaiting_analysis: 7,
  awaiting_review: 12,
  completed_reports: 96,
  consistency_issues: 18,
  high_severity_findings: 9,
  rca_inconclusive: 5,
  parser_dq_issues: 4,
};

export const DEMO_EVENTS: Event[] = [
  {
    id: 'ev-001',
    event_id: 'EVT-2026-0912',
    substation_name: 'North Grid SS',
    bay_name: 'Bay 12 — 220 kV Line',
    relay_tag: 'REL-L12-P1',
    feeder: 'L-220-12',
    event_datetime: '2026-09-02T14:22:11.452Z',
    nominal_voltage_kv: 220,
    nominal_frequency_hz: 50,
    description: 'Phase-A to ground fault on outgoing 220 kV line',
    status: 'AWAITING_REVIEW',
    decision_state: 'ENGINEER_REVIEW_REQUIRED',
    data_quality: 'ACCEPTABLE',
    fault_type: 'AG',
    severity_summary: 'HIGH',
    tags: ['line', '220kV', 'ground'],
  },
  {
    id: 'ev-002',
    event_id: 'EVT-2026-0908',
    substation_name: 'East Bay SS',
    bay_name: 'Bay 03 — Transformer',
    relay_tag: 'REL-T3-87',
    feeder: 'T-3',
    event_datetime: '2026-08-28T09:11:03.100Z',
    nominal_voltage_kv: 132,
    nominal_frequency_hz: 50,
    description: 'Differential trip — investigate CT mismatch',
    status: 'ANALYZING',
    data_quality: 'WARNING',
    fault_type: 'UNKNOWN',
    severity_summary: 'MEDIUM',
  },
  {
    id: 'ev-003',
    event_id: 'EVT-2026-0891',
    substation_name: 'North Grid SS',
    bay_name: 'Bay 07 — Feeder',
    relay_tag: 'REL-F07-51',
    feeder: 'F-07',
    event_datetime: '2026-08-15T18:44:55.800Z',
    nominal_voltage_kv: 33,
    nominal_frequency_hz: 50,
    description: 'OC trip cleared in 280 ms',
    status: 'CLOSED',
    decision_state: 'ANALYSIS_COMPLETE',
    data_quality: 'GOOD',
    fault_type: 'BC',
    severity_summary: 'LOW',
  },
  {
    id: 'ev-004',
    event_id: 'EVT-2026-0875',
    substation_name: 'West Ring SS',
    bay_name: 'Bay 01 — Bus Coupler',
    relay_tag: 'REL-BC-87B',
    event_datetime: '2026-08-10T03:02:41.000Z',
    nominal_voltage_kv: 220,
    status: 'FAILED',
    data_quality: 'POOR',
    fault_type: 'UNKNOWN',
    severity_summary: 'CRITICAL',
    description: 'COMTRADE parse failure — incomplete DAT',
  },
  {
    id: 'ev-005',
    event_id: 'EVT-2026-0860',
    substation_name: 'East Bay SS',
    bay_name: 'Bay 11 — Line',
    relay_tag: 'REL-L11-21',
    event_datetime: '2026-08-05T11:30:00.000Z',
    status: 'AWAITING_REVIEW',
    decision_state: 'INCONCLUSIVE',
    data_quality: 'WARNING',
    fault_type: 'ABG',
    severity_summary: 'HIGH',
    description: 'Zone 2 trip — RCA inconclusive pending settings verification',
  },
];

export const DEMO_FILES: EventFile[] = [
  {
    id: 'ef-001',
    event_id: 'ev-001',
    sha256: 'a3f8c91e2b7d4e6f0a1b2c3d4e5f6789abcdef0123456789abcdef0123456789',
    file_size: 245760,
    original_filename: 'NGSS_Bay12_20260902.cfg',
    source_type: 'COMTRADE',
    content_type: 'text/plain',
    storage_key: 'events/ev-001/NGSS_Bay12_20260902.cfg',
    upload_timestamp: '2026-09-02T15:01:00Z',
    immutable: true,
    status: 'VALIDATED',
  },
  {
    id: 'ef-002',
    event_id: 'ev-001',
    sha256: 'b7e4d20f3c8a5b1e9d6c4a2f0e8b7d5c3a1f9e7d5b3a19087fedcba987654321',
    file_size: 1048576,
    original_filename: 'NGSS_Bay12_20260902.dat',
    source_type: 'COMTRADE',
    content_type: 'application/octet-stream',
    storage_key: 'events/ev-001/NGSS_Bay12_20260902.dat',
    upload_timestamp: '2026-09-02T15:01:02Z',
    immutable: true,
    status: 'VALIDATED',
  },
  {
    id: 'ef-003',
    event_id: 'ev-001',
    sha256: 'c1d2e3f4a5b697887766554433221100ffeeddccbbaa99887766554433221100',
    file_size: 18432,
    original_filename: 'REL-L12-P1_settings_v3.2.json',
    source_type: 'SETTINGS',
    content_type: 'application/json',
    storage_key: 'events/ev-001/settings.json',
    upload_timestamp: '2026-09-02T15:05:00Z',
    immutable: true,
    status: 'STORED',
  },
];

export const DEMO_COMTRADE: ComtradeFile = {
  id: 'ct-001',
  event_id: 'ev-001',
  station_name: 'North Grid SS',
  recording_device: 'REL-L12-P1',
  revision_year: 1999,
  start_timestamp: '2026-09-02T14:22:11.200Z',
  trigger_timestamp: '2026-09-02T14:22:11.452Z',
  sample_rate_hz: 4000,
  total_samples: 8000,
  analog_channel_count: 8,
  digital_channel_count: 16,
  frequency_hz: 50,
  line_frequency_hz: 50,
  validation_status: 'VALID_WITH_WARNINGS',
  data_quality: 'ACCEPTABLE',
  parse_warnings: [
    'Digital channel DIG_12 name truncated in CFG',
    'Skew values absent — assumed 0 µs',
  ],
  format_detected: 'IEEE C37.111-1999 BINARY',
  support_status: 'SUPPORTED',
};

export const DEMO_SETTING_SOURCE: SettingSourceInfo = {
  source: 'ACTIVE_SETTING',
  version: 'v3.2 / Group 1',
  approval_status: 'APPROVED',
  effective_from: '2025-11-12T00:00:00Z',
  relay_tag: 'REL-L12-P1',
  checksum: 'e4f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5',
};

function genSine(
  n: number,
  freq: number,
  fs: number,
  amp: number,
  phaseDeg: number,
  faultStart: number,
  faultAmp: number,
): { t: number[]; y: number[] } {
  const t: number[] = [];
  const y: number[] = [];
  const ph = (phaseDeg * Math.PI) / 180;
  for (let i = 0; i < n; i++) {
    const tu = (i / fs) * 1e6;
    t.push(tu);
    const a = i >= faultStart ? faultAmp : amp;
    y.push(a * Math.sin(2 * Math.PI * freq * (i / fs) + ph));
  }
  return { t, y };
}

const N = 2000;
const FS = 4000;
const faultIdx = 800;

const Ia = genSine(N, 50, FS, 1.0, 0, faultIdx, 8.5);
const Ib = genSine(N, 50, FS, 1.0, -120, faultIdx, 1.2);
const Ic = genSine(N, 50, FS, 1.0, 120, faultIdx, 1.1);
const Va = genSine(N, 50, FS, 1.0, 0, faultIdx, 0.35);
const Vb = genSine(N, 50, FS, 1.0, -120, faultIdx, 0.95);
const Vc = genSine(N, 50, FS, 1.0, 120, faultIdx, 0.98);

export const DEMO_WAVEFORMS: WaveformChannelData[] = [
  {
    channel: {
      id: 'ch-ia',
      comtrade_file_id: 'ct-001',
      channel_index: 1,
      channel_type: 'ANALOG',
      name: 'Ia',
      phase: 'A',
      units: 'kA',
      mapped_signal: 'Ia',
    },
    samples: Ia.y,
    time_us: Ia.t,
  },
  {
    channel: {
      id: 'ch-ib',
      comtrade_file_id: 'ct-001',
      channel_index: 2,
      channel_type: 'ANALOG',
      name: 'Ib',
      phase: 'B',
      units: 'kA',
      mapped_signal: 'Ib',
    },
    samples: Ib.y,
    time_us: Ib.t,
  },
  {
    channel: {
      id: 'ch-ic',
      comtrade_file_id: 'ct-001',
      channel_index: 3,
      channel_type: 'ANALOG',
      name: 'Ic',
      phase: 'C',
      units: 'kA',
      mapped_signal: 'Ic',
    },
    samples: Ic.y,
    time_us: Ic.t,
  },
  {
    channel: {
      id: 'ch-va',
      comtrade_file_id: 'ct-001',
      channel_index: 4,
      channel_type: 'ANALOG',
      name: 'Va',
      phase: 'A',
      units: 'kV',
      mapped_signal: 'Va',
    },
    samples: Va.y,
    time_us: Va.t,
  },
  {
    channel: {
      id: 'ch-vb',
      comtrade_file_id: 'ct-001',
      channel_index: 5,
      channel_type: 'ANALOG',
      name: 'Vb',
      phase: 'B',
      units: 'kV',
      mapped_signal: 'Vb',
    },
    samples: Vb.y,
    time_us: Vb.t,
  },
  {
    channel: {
      id: 'ch-vc',
      comtrade_file_id: 'ct-001',
      channel_index: 6,
      channel_type: 'ANALOG',
      name: 'Vc',
      phase: 'C',
      units: 'kV',
      mapped_signal: 'Vc',
    },
    samples: Vc.y,
    time_us: Vc.t,
  },
  {
    channel: {
      id: 'ch-trip',
      comtrade_file_id: 'ct-001',
      channel_index: 1,
      channel_type: 'DIGITAL',
      name: 'TRIP',
      mapped_signal: 'TRIP',
    },
    samples: Array.from({ length: N }, (_, i) => (i >= 920 && i < 1400 ? 1 : 0)),
    time_us: Ia.t,
  },
  {
    channel: {
      id: 'ch-52a',
      comtrade_file_id: 'ct-001',
      channel_index: 2,
      channel_type: 'DIGITAL',
      name: '52a',
      mapped_signal: '52a',
    },
    samples: Array.from({ length: N }, (_, i) => (i < 980 ? 1 : 0)),
    time_us: Ia.t,
  },
];

export const DEMO_MARKERS: WaveformMarker[] = [
  { t_us: (faultIdx / FS) * 1e6, label: 'Fault inception', color: '#d64545' },
  { t_us: (920 / FS) * 1e6, label: 'Trip assert', color: '#e07a3d' },
  { t_us: (980 / FS) * 1e6, label: 'Breaker open', color: '#d4a017' },
];

export const DEMO_TIMELINE: TimelineEntry[] = [
  {
    id: 'tl-1',
    event_id: 'ev-001',
    sequence: 1,
    t_us: 0,
    absolute_time: '2026-09-02T14:22:11.200Z',
    event_type: 'RECORD_START',
    source: 'COMTRADE',
    label: 'Recording start',
    description: 'Pre-fault capture begins',
    confidence: 1,
  },
  {
    id: 'tl-2',
    event_id: 'ev-001',
    sequence: 2,
    t_us: 200000,
    absolute_time: '2026-09-02T14:22:11.400Z',
    event_type: 'FAULT_INCEPTION',
    source: 'SIGNAL',
    label: 'Fault inception (AG)',
    description: 'Phase A current rise; Va collapse detected',
    confidence: 0.94,
    evidence_ids: ['evd-01', 'evd-02'],
  },
  {
    id: 'tl-3',
    event_id: 'ev-001',
    sequence: 3,
    t_us: 212000,
    absolute_time: '2026-09-02T14:22:11.412Z',
    event_type: 'PICKUP',
    source: 'DIGITAL',
    label: 'Z1 / 21 pickup',
    description: 'Distance Zone 1 pickup asserted',
    confidence: 0.91,
  },
  {
    id: 'tl-4',
    event_id: 'ev-001',
    sequence: 4,
    t_us: 230000,
    absolute_time: '2026-09-02T14:22:11.430Z',
    event_type: 'TRIP',
    source: 'DIGITAL',
    label: 'Trip command',
    description: 'TRIP digital channel asserted',
    confidence: 0.98,
  },
  {
    id: 'tl-5',
    event_id: 'ev-001',
    sequence: 5,
    t_us: 245000,
    absolute_time: '2026-09-02T14:22:11.445Z',
    event_type: 'BREAKER_OPEN',
    source: 'DIGITAL',
    label: 'Breaker open (52a)',
    description: '52a drops; interrupting time ≈ 15 ms',
    confidence: 0.96,
  },
  {
    id: 'tl-6',
    event_id: 'ev-001',
    sequence: 6,
    t_us: 280000,
    absolute_time: '2026-09-02T14:22:11.480Z',
    event_type: 'FAULT_CLEARED',
    source: 'SIGNAL',
    label: 'Fault cleared',
    description: 'Current decayed below residual threshold',
    confidence: 0.89,
  },
];

export const DEMO_MEASUREMENTS: Measurement[] = [
  { id: 'm1', event_id: 'ev-001', quantity: 'Ia_rms', phase: 'A', value: 6.82, unit: 'kA', algorithm: 'DFT', quality: 'GOOD' },
  { id: 'm2', event_id: 'ev-001', quantity: 'Ib_rms', phase: 'B', value: 0.91, unit: 'kA', algorithm: 'DFT', quality: 'GOOD' },
  { id: 'm3', event_id: 'ev-001', quantity: 'Ic_rms', phase: 'C', value: 0.88, unit: 'kA', algorithm: 'DFT', quality: 'GOOD' },
  { id: 'm4', event_id: 'ev-001', quantity: 'Va_rms', phase: 'A', value: 48.2, unit: 'kV', algorithm: 'DFT', quality: 'GOOD' },
  { id: 'm5', event_id: 'ev-001', quantity: 'Vb_rms', phase: 'B', value: 126.4, unit: 'kV', algorithm: 'DFT', quality: 'GOOD' },
  { id: 'm6', event_id: 'ev-001', quantity: 'Vc_rms', phase: 'C', value: 125.9, unit: 'kV', algorithm: 'DFT', quality: 'GOOD' },
  {
    id: 'm7',
    event_id: 'ev-001',
    quantity: 'Ia_phasor',
    phase: 'A',
    value: 6.82,
    unit: 'kA',
    vector: { mag: 6.82, angle_deg: -12.4 },
    algorithm: 'DFT',
    quality: 'GOOD',
  },
  {
    id: 'm8',
    event_id: 'ev-001',
    quantity: 'Va_phasor',
    phase: 'A',
    value: 48.2,
    unit: 'kV',
    vector: { mag: 48.2, angle_deg: -98.1 },
    algorithm: 'DFT',
    quality: 'GOOD',
  },
  { id: 'm9', event_id: 'ev-001', quantity: 'I1', phase: 'POS', value: 2.41, unit: 'kA', algorithm: 'SYM', quality: 'GOOD' },
  { id: 'm10', event_id: 'ev-001', quantity: 'I2', phase: 'NEG', value: 2.28, unit: 'kA', algorithm: 'SYM', quality: 'GOOD' },
  { id: 'm11', event_id: 'ev-001', quantity: 'I0', phase: 'ZERO', value: 2.15, unit: 'kA', algorithm: 'SYM', quality: 'GOOD' },
  { id: 'm12', event_id: 'ev-001', quantity: 'V1', phase: 'POS', value: 98.4, unit: 'kV', algorithm: 'SYM', quality: 'GOOD' },
  { id: 'm13', event_id: 'ev-001', quantity: 'V0', phase: 'ZERO', value: 42.1, unit: 'kV', algorithm: 'SYM', quality: 'ACCEPTABLE' },
  {
    id: 'm14',
    event_id: 'ev-001',
    quantity: 'Z_AG',
    phase: 'A',
    value: 7.12,
    unit: 'Ω',
    vector: { mag: 7.12, angle_deg: 78.5 },
    algorithm: 'LOOP',
    quality: 'GOOD',
  },
  { id: 'm15', event_id: 'ev-001', quantity: 'R_fault', phase: 'A', value: 1.42, unit: 'Ω', algorithm: 'LOOP', quality: 'ACCEPTABLE' },
  { id: 'm16', event_id: 'ev-001', quantity: 'freq', value: 49.97, unit: 'Hz', algorithm: 'ZCD', quality: 'GOOD' },
];

export const DEMO_PROTECTION: ProtectionOperation[] = [
  {
    id: 'po-1',
    event_id: 'ev-001',
    element: 'Z1',
    function_code: '21',
    operation_type: 'PICKUP',
    asserted: true,
    t_pickup_us: 212000,
    expected: true,
    confidence: 0.93,
    details: { zone: 1, reach_pct: 82 },
  },
  {
    id: 'po-2',
    event_id: 'ev-001',
    element: 'Z1',
    function_code: '21',
    operation_type: 'TRIP',
    asserted: true,
    t_trip_us: 230000,
    expected: true,
    confidence: 0.95,
  },
  {
    id: 'po-3',
    event_id: 'ev-001',
    element: '50N',
    function_code: '50N',
    operation_type: 'PICKUP',
    asserted: true,
    t_pickup_us: 208000,
    expected: true,
    confidence: 0.88,
  },
  {
    id: 'po-4',
    event_id: 'ev-001',
    element: 'BF',
    function_code: '50BF',
    operation_type: 'TARGET',
    asserted: false,
    expected: false,
    confidence: 0.99,
    breaker_assessment: 'NORMAL',
  },
];

export const DEMO_FINDINGS: ConsistencyFinding[] = [
  {
    id: 'cf-1',
    finding_id: 'FND-001',
    event_id: 'ev-001',
    element: 'Z1',
    check_type: 'ZONE_REACH',
    setting_source: 'ACTIVE_SETTING v3.2 / Group 1',
    setting_version: 'v3.2',
    expected: { reach_ohm: 8.5, time_ms: 0 },
    observed: { Z_mag: 7.12, angle_deg: 78.5, operate: true },
    status: 'CONSISTENT',
    severity: 'INFO',
    explanation: 'Measured AG loop impedance within Z1 mho characteristic.',
    confidence: 0.92,
    evidence_ids: ['evd-01', 'evd-04'],
    rule_version: 'consistency-1.4.0',
  },
  {
    id: 'cf-2',
    finding_id: 'FND-002',
    event_id: 'ev-001',
    element: 'Z1',
    check_type: 'TIME_DELAY',
    setting_source: 'ACTIVE_SETTING v3.2 / Group 1',
    setting_version: 'v3.2',
    expected: { delay_ms: 0 },
    observed: { pickup_to_trip_ms: 18 },
    status: 'CONSISTENT',
    severity: 'INFO',
    explanation: 'Instantaneous zone trip; observed 18 ms includes relay processing.',
    confidence: 0.9,
    evidence_ids: ['evd-03'],
  },
  {
    id: 'cf-3',
    finding_id: 'FND-003',
    event_id: 'ev-001',
    element: '50N',
    check_type: 'PICKUP_THRESHOLD',
    setting_source: 'ACTIVE_SETTING v3.2 / Group 1',
    setting_version: 'v3.2',
    expected: { pickup_A: 0.5 },
    observed: { I0_A: 2.15, pickup: true },
    status: 'CONSISTENT',
    severity: 'LOW',
    explanation: 'Residual current exceeded 50N pickup.',
    confidence: 0.87,
  },
  {
    id: 'cf-4',
    finding_id: 'FND-004',
    event_id: 'ev-001',
    element: '52',
    check_type: 'BREAKER_TIME',
    setting_source: 'BASE_SETTINGS / Breaker nameplate',
    setting_version: 'nameplate',
    expected: { open_ms: 40 },
    observed: { open_ms: 15 },
    status: 'CONSISTENT',
    severity: 'INFO',
    explanation: 'Breaker interrupting time within expected range.',
    confidence: 0.96,
    evidence_ids: ['evd-05'],
  },
  {
    id: 'cf-5',
    finding_id: 'FND-005',
    event_id: 'ev-001',
    element: '67N',
    check_type: 'DIRECTION',
    setting_source: 'ACTIVE_SETTING v3.2 / Group 1',
    setting_version: 'v3.2',
    expected: { direction: 'FORWARD', enabled: true },
    observed: { polarizing: 'WEAK', direction: 'UNVERIFIABLE' },
    status: 'UNVERIFIABLE',
    severity: 'MEDIUM',
    explanation: 'Weak polarizing voltage during AG fault — directionality not confirmed.',
    confidence: 0.55,
    evidence_ids: ['evd-06'],
  },
];

export const DEMO_FAULT: FaultClassification = {
  id: 'fc-1',
  event_id: 'ev-001',
  fault_type: 'AG',
  status: 'CLASSIFIED',
  involved_phases: ['A'],
  ground_involved: true,
  distance_km: 12.4,
  impedance_ohm: 7.12,
  impedance_angle_deg: 78.5,
  duration_ms: 80,
  confidence: 0.93,
  confidence_level: 'HIGH',
  explanation: 'High I0, Va collapse, AB/AC loops stable — AG classification.',
  is_primary: true,
};

export const DEMO_RCA: RcaHypothesis[] = [
  {
    id: 'rca-1',
    event_id: 'ev-001',
    hypothesis_code: 'H1',
    title: 'Correct Zone-1 AG trip — permanent line fault',
    statement:
      'A phase-A to ground fault occurred within Zone 1 reach. Distance and residual OC elements operated as designed; breaker cleared normally.',
    status: 'PROBABLE',
    rank: 1,
    confidence: 0.88,
    confidence_level: 'HIGH',
    supporting_evidence_ids: ['evd-01', 'evd-02', 'evd-03', 'evd-04', 'evd-05'],
    contradicting_evidence_ids: [],
    missing_evidence: ['Line patrol report', 'Post-fault insulation resistance'],
    causal_chain: [
      'AG fault inception at ~12.4 km',
      'Z1 + 50N pickup',
      'Trip in 18 ms from pickup',
      'Breaker open in 15 ms',
      'Fault cleared',
    ],
    recommended_actions: [
      'Dispatch line patrol for tower/insulator inspection near 12 km mark',
      'Confirm setting group 1 was active at event time via SOE',
    ],
    explanation: 'Primary evidence chain is coherent; remaining uncertainty is root physical cause on the line.',
  },
  {
    id: 'rca-2',
    event_id: 'ev-001',
    hypothesis_code: 'H2',
    title: 'CT saturation false residual — incorrect 50N contribution',
    statement:
      'Severe CT saturation on phase A could inflate I0 and contribute to residual element pickup, though Z1 loop impedance still indicates a real AG fault.',
    status: 'UNLIKELY',
    rank: 2,
    confidence: 0.22,
    confidence_level: 'LOW',
    supporting_evidence_ids: [],
    contradicting_evidence_ids: ['evd-01', 'evd-02'],
    missing_evidence: ['CT saturation waveform markers', 'Burden measurement'],
    recommended_actions: ['Review CT ratio/burden if recurrence observed'],
  },
  {
    id: 'rca-3',
    event_id: 'ev-001',
    hypothesis_code: 'H3',
    title: 'Wrong setting group active',
    statement:
      'If Group 2 were active, Z1 reach would differ; current evidence uses Group 1 approved settings.',
    status: 'POSSIBLE',
    rank: 3,
    confidence: 0.35,
    confidence_level: 'LOW',
    supporting_evidence_ids: [],
    contradicting_evidence_ids: ['evd-07'],
    missing_evidence: ['Relay SOE setting-group change log'],
    recommended_actions: ['Pull relay event report / SOE for active group at T0'],
  },
];

export const DEMO_EVIDENCE: EvidenceItem[] = [
  {
    id: 'evd-01',
    event_id: 'ev-001',
    evidence_key: 'E-IA-RISE',
    source_type: 'COMTRADE',
    polarity: 'SUPPORTING',
    title: 'Phase A current rise at fault inception',
    summary: 'Ia RMS increased from 0.95 kA to 6.82 kA within 1 cycle of t=200 ms.',
    confidence: 0.97,
    t_us: 200000,
    references: { channel: 'Ia', window_ms: [200, 220] },
    children: [
      {
        id: 'evd-01a',
        event_id: 'ev-001',
        evidence_key: 'E-IA-DFT',
        source_type: 'CALCULATION',
        polarity: 'SUPPORTING',
        title: 'DFT RMS window',
        summary: 'Full-cycle DFT centered at 210 ms.',
        confidence: 0.95,
        t_us: 210000,
      },
    ],
  },
  {
    id: 'evd-02',
    event_id: 'ev-001',
    evidence_key: 'E-VA-COLLAPSE',
    source_type: 'COMTRADE',
    polarity: 'SUPPORTING',
    title: 'Phase A voltage collapse',
    summary: 'Va RMS dropped to 48.2 kV (~38% nominal).',
    confidence: 0.96,
    t_us: 200000,
  },
  {
    id: 'evd-03',
    event_id: 'ev-001',
    evidence_key: 'E-TRIP',
    source_type: 'COMTRADE',
    polarity: 'SUPPORTING',
    title: 'TRIP digital asserted',
    summary: 'TRIP channel transition at t=230 ms.',
    confidence: 0.99,
    t_us: 230000,
  },
  {
    id: 'evd-04',
    event_id: 'ev-001',
    evidence_key: 'E-Z1-REACH',
    source_type: 'PROTECTION_RULE',
    polarity: 'SUPPORTING',
    title: 'Z_AG inside Zone 1 characteristic',
    summary: '7.12 ∠78.5° Ω within Z1 mho (8.5 Ω @ 80°).',
    confidence: 0.92,
    references: { setting: 'Z1_REACH', version: 'v3.2' },
  },
  {
    id: 'evd-05',
    event_id: 'ev-001',
    evidence_key: 'E-52A',
    source_type: 'COMTRADE',
    polarity: 'SUPPORTING',
    title: 'Breaker open confirmation',
    summary: '52a dropped 15 ms after trip.',
    confidence: 0.96,
    t_us: 245000,
  },
  {
    id: 'evd-06',
    event_id: 'ev-001',
    evidence_key: 'E-POL-WEAK',
    source_type: 'CALCULATION',
    polarity: 'NEUTRAL',
    title: 'Weak polarizing voltage for 67N',
    summary: 'Vpol magnitude below confidence threshold during fault.',
    confidence: 0.7,
  },
  {
    id: 'evd-07',
    event_id: 'ev-001',
    evidence_key: 'E-SET-SRC',
    source_type: 'ACTIVE_SETTING',
    polarity: 'SUPPORTING',
    title: 'Approved Group 1 settings used',
    summary: 'Analysis bound to ACTIVE_SETTING v3.2 checksum e4f1…',
    confidence: 0.85,
  },
  {
    id: 'evd-08',
    event_id: 'ev-001',
    evidence_key: 'E-PATROL',
    source_type: 'HISTORICAL_EVENT',
    polarity: 'MISSING',
    title: 'Line patrol report not available',
    summary: 'Physical root cause unverified until field inspection returns.',
    confidence: 0,
  },
];

export const DEMO_REPORT: Report = {
  id: 'rpt-1',
  event_id: 'ev-001',
  report_type: 'RCA',
  title: 'Disturbance Report — EVT-2026-0912',
  status: 'DRAFT',
  summary: 'AG fault on L-220-12 cleared by Zone 1. Breaker performance normal. Field patrol recommended.',
  generated_at: '2026-09-02T16:40:00Z',
  html_content: `
    <article class="rca-report">
      <h1>Disturbance Record Analysis Report</h1>
      <p><strong>Event:</strong> EVT-2026-0912 &nbsp;|&nbsp; <strong>Station:</strong> North Grid SS &nbsp;|&nbsp; <strong>Bay:</strong> Bay 12</p>
      <h2>1. What happened</h2>
      <p>A phase-A to ground fault was recorded on feeder L-220-12 at 2026-09-02 14:22:11.452 UTC.
      Fault duration ≈ 80 ms. Cleared by distance Zone 1 trip and breaker open.</p>
      <h2>2. Why (primary hypothesis)</h2>
      <p><em>PROBABLE (confidence 0.88):</em> Correct Zone-1 AG trip for a permanent line fault near 12.4 km.</p>
      <h2>3. Settings used</h2>
      <p>ACTIVE_SETTING v3.2 / Group 1 — APPROVED — effective 2025-11-12 — relay REL-L12-P1</p>
      <h2>4. Consistency</h2>
      <ul>
        <li>Z1 reach — CONSISTENT</li>
        <li>Z1 time — CONSISTENT</li>
        <li>50N pickup — CONSISTENT</li>
        <li>67N direction — UNVERIFIABLE (weak polarizing)</li>
      </ul>
      <h2>5. Uncertainty &amp; verify</h2>
      <ul>
        <li>Missing: line patrol report, post-fault IR</li>
        <li>Confirm active setting group via SOE</li>
        <li>67N directionality not confirmed</li>
      </ul>
    </article>
  `,
};

export const DEMO_JOB: AnalysisJob = {
  id: 'job-001',
  event_id: 'ev-001',
  status: 'RUNNING',
  stage: 'FAULT_CLASSIFICATION',
  progress: 72,
  current_message: 'Classifying fault type from sequence components…',
  started_at: '2026-09-02T15:10:00Z',
  component_versions: {
    parser: 'comtrade-2.1.0',
    rules: 'consistency-1.4.0',
    rca: 'rca-engine-0.9.2',
  },
  stages: [
    { name: 'UPLOAD', label: 'Upload', status: 'done' },
    { name: 'FILE_DETECTION', label: 'File Detection', status: 'done' },
    { name: 'COMTRADE_VALIDATION', label: 'COMTRADE Validation', status: 'done' },
    { name: 'PARSING', label: 'Parsing', status: 'done' },
    { name: 'SIGNAL_PROCESSING', label: 'Signal Processing', status: 'done' },
    { name: 'EVENT_RECONSTRUCTION', label: 'Event Reconstruction', status: 'done' },
    { name: 'PROTECTION_ANALYSIS', label: 'Protection Analysis', status: 'done' },
    { name: 'CONSISTENCY_CHECKER', label: 'Consistency Checker', status: 'done' },
    { name: 'FAULT_CLASSIFICATION', label: 'Fault Classification', status: 'running' },
    { name: 'RCA', label: 'RCA', status: 'pending' },
    { name: 'EVIDENCE', label: 'Evidence', status: 'pending' },
    { name: 'REPORT', label: 'Report', status: 'pending' },
  ],
};

export const DEMO_SUBSTATIONS: Substation[] = [
  { id: 'ss-1', code: 'NGSS', name: 'North Grid SS', region: 'North', voltage_levels_kv: [220, 132], is_active: true },
  { id: 'ss-2', code: 'EBSS', name: 'East Bay SS', region: 'East', voltage_levels_kv: [132, 33], is_active: true },
  { id: 'ss-3', code: 'WRSS', name: 'West Ring SS', region: 'West', voltage_levels_kv: [220], is_active: true },
];

export const DEMO_BAYS: Bay[] = [
  { id: 'bay-1', substation_id: 'ss-1', code: 'B12', name: 'Bay 12 — 220 kV Line', feeder_name: 'L-220-12', voltage_kv: 220, bay_type: 'LINE', is_active: true },
  { id: 'bay-2', substation_id: 'ss-1', code: 'B07', name: 'Bay 07 — Feeder', feeder_name: 'F-07', voltage_kv: 33, bay_type: 'FEEDER', is_active: true },
  { id: 'bay-3', substation_id: 'ss-2', code: 'B03', name: 'Bay 03 — Transformer', voltage_kv: 132, bay_type: 'TRANSFORMER', is_active: true },
];

export const DEMO_ASSETS: Asset[] = [
  { id: 'as-1', substation_id: 'ss-1', bay_id: 'bay-1', asset_tag: 'L-220-12', name: 'North–East 220 kV Line', asset_type: 'LINE', nominal_voltage_kv: 220, is_active: true },
  { id: 'as-2', substation_id: 'ss-2', bay_id: 'bay-3', asset_tag: 'T-3', name: 'Transformer T3', asset_type: 'TRANSFORMER', nominal_voltage_kv: 132, is_active: true },
];

export const DEMO_RELAYS: Relay[] = [
  { id: 'rel-1', substation_id: 'ss-1', bay_id: 'bay-1', relay_tag: 'REL-L12-P1', name: 'Line Dist. Primary', manufacturer: 'SEL', model: '421', firmware_version: 'R317', protection_functions: ['21', '50/51', '67N', '50BF'], is_active: true },
  { id: 'rel-2', substation_id: 'ss-2', bay_id: 'bay-3', relay_tag: 'REL-T3-87', name: 'Transformer Diff', manufacturer: 'GE', model: 'T60', firmware_version: '7.6', protection_functions: ['87T', '50/51', '49'], is_active: true },
];

export const DEMO_BREAKERS: Breaker[] = [
  { id: 'brk-1', substation_id: 'ss-1', bay_id: 'bay-1', breaker_tag: 'CB-12', name: 'Line Breaker 12', rated_voltage_kv: 220, expected_open_time_ms: 40, is_active: true },
  { id: 'brk-2', substation_id: 'ss-2', bay_id: 'bay-3', breaker_tag: 'CB-T3', name: 'Transformer Breaker T3', rated_voltage_kv: 132, expected_open_time_ms: 50, is_active: true },
];

export const DEMO_SETTING_VERSIONS: SettingVersion[] = [
  { id: 'sv-1', relay_id: 'rel-1', version_label: 'v3.2', version_number: 3, source: 'vendor export', approval_status: 'APPROVED', effective_from: '2025-11-12T00:00:00Z', checksum_sha256: 'e4f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1' },
  { id: 'sv-2', relay_id: 'rel-1', version_label: 'v3.1', version_number: 2, source: 'manual', approval_status: 'SUPERSEDED', effective_from: '2024-06-01T00:00:00Z' },
];

export const DEMO_SETTING_GROUPS: SettingGroup[] = [
  { id: 'sg-1', relay_id: 'rel-1', group_number: 1, name: 'Group 1 — Normal', is_active: true },
  { id: 'sg-2', relay_id: 'rel-1', group_number: 2, name: 'Group 2 — Contingency', is_active: false },
];

export const DEMO_RULES: RuleVersion[] = [
  { id: 'rv-1', rule_family: 'CONSISTENCY', version: '1.4.0', name: 'Consistency Checker', is_active: true, description: 'Zone reach, timing, direction checks' },
  { id: 'rv-2', rule_family: 'PROTECTION', version: '2.1.0', name: 'Protection Assessment', is_active: true },
  { id: 'rv-3', rule_family: 'RCA', version: '0.9.2', name: 'RCA Hypothesis Engine', is_active: true },
];

export const DEMO_MODELS: ModelVersion[] = [
  { id: 'mv-1', model_name: 'fault-classifier', version: '1.2.0', model_type: 'CLASSIFIER', is_active: true, framework: 'sklearn', metrics: { f1: 0.94 } },
  { id: 'mv-2', model_name: 'anomaly-detector', version: '0.8.1', model_type: 'ANOMALY', is_active: false, framework: 'pytorch' },
];

export const DEMO_USERS: User[] = [
  DEMO_USER,
  { id: 'u-002', username: 'a.analyst', email: 'a.analyst@utility.local', full_name: 'A. Analyst', role: 'ANALYST', is_active: true },
  { id: 'u-003', username: 'r.approver', email: 'r.approver@utility.local', full_name: 'R. Approver', role: 'APPROVER', is_active: true },
  { id: 'u-004', username: 'admin', email: 'admin@utility.local', full_name: 'System Admin', role: 'ADMIN', is_active: true },
];

export const DEMO_AUDIT: AuditLogEntry[] = [
  { id: 'al-1', user_id: 'u-001', username: 's.engineer', timestamp: '2026-09-04T06:00:00Z', action: 'LOGIN', object_type: 'User', object_id: 'u-001', ip_address: '10.20.1.44' },
  { id: 'al-2', user_id: 'u-001', username: 's.engineer', timestamp: '2026-09-02T15:01:00Z', action: 'UPLOAD', object_type: 'EventFile', object_id: 'ef-001', ip_address: '10.20.1.44' },
  { id: 'al-3', user_id: 'u-001', username: 's.engineer', timestamp: '2026-09-02T16:45:00Z', action: 'REVIEW', object_type: 'Event', object_id: 'ev-001', ip_address: '10.20.1.44' },
  { id: 'al-4', user_id: 'u-003', username: 'r.approver', timestamp: '2026-08-16T10:00:00Z', action: 'APPROVE', object_type: 'SettingVersion', object_id: 'sv-1', ip_address: '10.20.1.12' },
];
