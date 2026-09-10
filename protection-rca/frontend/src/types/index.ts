/** Shared TypeScript types matching backend domain concepts. */

export type DataQuality = 'GOOD' | 'ACCEPTABLE' | 'WARNING' | 'POOR' | 'INVALID';

export type ValidationStatus =
  | 'VALID'
  | 'VALID_WITH_WARNINGS'
  | 'PARTIALLY_SUPPORTED'
  | 'NOT_VALIDATED'
  | 'INVALID';

export type ConsistencyStatus =
  | 'CONSISTENT'
  | 'INCONSISTENT'
  | 'UNVERIFIABLE'
  | 'DATA_QUALITY_ISSUE';

export type Severity = 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';

export type FaultType =
  | 'AG'
  | 'BG'
  | 'CG'
  | 'AB'
  | 'BC'
  | 'CA'
  | 'ABG'
  | 'BCG'
  | 'CAG'
  | 'ABC'
  | 'ABCG'
  | 'UNKNOWN';

export type ClassificationStatus =
  | 'CLASSIFIED'
  | 'PROBABLE'
  | 'INCONCLUSIVE'
  | 'UNKNOWN';

export type HypothesisStatus =
  | 'CONFIRMED'
  | 'PROBABLE'
  | 'POSSIBLE'
  | 'UNLIKELY'
  | 'INCONCLUSIVE';

export type DecisionState =
  | 'ANALYSIS_COMPLETE'
  | 'ANALYSIS_COMPLETE_WITH_WARNINGS'
  | 'INCONCLUSIVE'
  | 'DATA_INSUFFICIENT'
  | 'UNSUPPORTED_FORMAT'
  | 'ENGINEER_REVIEW_REQUIRED';

export type ConfidenceLevel = 'HIGH' | 'MEDIUM' | 'LOW' | 'INCONCLUSIVE';

export type ReviewAction =
  | 'ACCEPT'
  | 'MODIFY'
  | 'REJECT'
  | 'INCONCLUSIVE'
  | 'REQUEST_FIELD_INVESTIGATION';

export type JobStage =
  | 'UPLOAD'
  | 'FILE_DETECTION'
  | 'COMTRADE_VALIDATION'
  | 'PARSING'
  | 'SIGNAL_PROCESSING'
  | 'EVENT_RECONSTRUCTION'
  | 'PROTECTION_ANALYSIS'
  | 'CONSISTENCY_CHECKER'
  | 'FAULT_CLASSIFICATION'
  | 'RCA'
  | 'EVIDENCE'
  | 'REPORT'
  | 'COMPLETE'
  | 'FAILED';

export type StageStatus = 'pending' | 'running' | 'done' | 'failed' | 'skipped';

export type UserRole =
  | 'VIEWER'
  | 'ANALYST'
  | 'PROTECTION_ENGINEER'
  | 'APPROVER'
  | 'ADMIN';

export type EventStatus =
  | 'UPLOADED'
  | 'PARSING'
  | 'ANALYZING'
  | 'AWAITING_REVIEW'
  | 'REVIEW'
  | 'CLOSED'
  | 'FAILED';

export interface User {
  id: string;
  username: string;
  email: string;
  full_name?: string | null;
  role: UserRole;
  is_active: boolean;
  last_login_at?: string | null;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface Substation {
  id: string;
  code: string;
  name: string;
  region?: string | null;
  voltage_levels_kv?: number[] | null;
  is_active: boolean;
}

export interface Bay {
  id: string;
  substation_id: string;
  code: string;
  name: string;
  feeder_name?: string | null;
  voltage_kv?: number | null;
  bay_type?: string | null;
  is_active: boolean;
}

export interface Asset {
  id: string;
  substation_id?: string | null;
  bay_id?: string | null;
  asset_tag: string;
  name: string;
  asset_type: string;
  nominal_voltage_kv?: number | null;
  is_active: boolean;
}

export interface Relay {
  id: string;
  substation_id?: string | null;
  bay_id?: string | null;
  relay_tag: string;
  name: string;
  manufacturer?: string | null;
  model?: string | null;
  firmware_version?: string | null;
  protection_functions?: string[] | null;
  is_active: boolean;
}

export interface Breaker {
  id: string;
  substation_id?: string | null;
  bay_id?: string | null;
  breaker_tag: string;
  name: string;
  rated_voltage_kv?: number | null;
  expected_open_time_ms?: number | null;
  is_active: boolean;
}

export interface Event {
  id: string;
  event_id: string;
  substation_id?: string | null;
  bay_id?: string | null;
  asset_id?: string | null;
  relay_id?: string | null;
  breaker_id?: string | null;
  engineer_id?: string | null;
  feeder?: string | null;
  event_datetime?: string | null;
  nominal_voltage_kv?: number | null;
  nominal_frequency_hz?: number | null;
  description?: string | null;
  status: EventStatus;
  decision_state?: DecisionState | null;
  data_quality?: DataQuality | null;
  tags?: string[] | null;
  extra?: Record<string, unknown> | null;
  /* Joined display fields (API enrichment / mock) */
  substation_name?: string | null;
  bay_name?: string | null;
  relay_tag?: string | null;
  fault_type?: FaultType | null;
  severity_summary?: Severity | null;
}

export interface EventFile {
  id: string;
  event_id: string;
  sha256: string;
  file_size: number;
  original_filename: string;
  source_type: string;
  content_type?: string | null;
  storage_key: string;
  upload_timestamp: string;
  immutable: boolean;
  status?: string;
  file_metadata?: {
    end_label?: string;
    [key: string]: unknown;
  } | null;
}

export interface ComtradeFile {
  id: string;
  event_id: string;
  station_name?: string | null;
  recording_device?: string | null;
  revision_year?: number | null;
  start_timestamp?: string | null;
  trigger_timestamp?: string | null;
  sample_rate_hz?: number | null;
  total_samples?: number | null;
  analog_channel_count?: number | null;
  digital_channel_count?: number | null;
  frequency_hz?: number | null;
  line_frequency_hz?: number | null;
  validation_status?: ValidationStatus | null;
  data_quality?: DataQuality | null;
  parse_warnings?: string[] | null;
  format_detected?: string | null;
  support_status?: string | null;
}

export interface ComtradeChannel {
  id: string;
  comtrade_file_id: string;
  channel_index: number;
  channel_type: 'ANALOG' | 'DIGITAL';
  name: string;
  phase?: string | null;
  units?: string | null;
  mapped_signal?: string | null;
  /** COMTRADE CFG PS field when available (P / S). */
  ps?: string | null;
  primary?: number | null;
  secondary_ratio?: number | null;
}

export interface WaveformChannelData {
  channel: ComtradeChannel;
  samples: Float32Array | number[];
  time_us: Float32Array | number[];
}

export interface WaveformMarker {
  t_us: number;
  label: string;
  color?: string;
}

export interface Measurement {
  id: string;
  event_id: string;
  quantity: string;
  phase?: string | null;
  value?: number | null;
  unit?: string | null;
  timestamp?: string | null;
  algorithm?: string | null;
  quality?: DataQuality | null;
  vector?: { mag?: number; angle_deg?: number; [k: string]: unknown } | null;
}

export interface TimelineEntry {
  id: string;
  event_id: string;
  sequence: number;
  t_us?: number | null;
  absolute_time?: string | null;
  event_type: string;
  source?: string | null;
  label?: string | null;
  description?: string | null;
  confidence?: number | null;
  evidence_ids?: string[] | null;
  details?: Record<string, unknown> | null;
}

export interface ProtectionOperation {
  id: string;
  event_id: string;
  relay_id?: string | null;
  element: string;
  function_code?: string | null;
  operation_type: string;
  asserted: boolean;
  t_pickup_us?: number | null;
  t_trip_us?: number | null;
  expected?: boolean | null;
  breaker_assessment?: string | null;
  confidence?: number | null;
  details?: Record<string, unknown> | null;
}

export interface ConsistencyFinding {
  id: string;
  finding_id: string;
  event_id: string;
  element: string;
  check_type: string;
  setting_source?: string | null;
  setting_version?: string | null;
  expected?: Record<string, unknown> | string | null;
  observed?: Record<string, unknown> | string | null;
  status: ConsistencyStatus;
  severity: Severity;
  evidence_ids?: string[] | null;
  explanation?: string | null;
  confidence?: number | null;
  rule_version?: string | null;
}

export interface FaultClassification {
  id: string;
  event_id: string;
  fault_type: FaultType;
  status: ClassificationStatus;
  involved_phases?: string[] | null;
  ground_involved?: boolean | null;
  distance_km?: number | null;
  location_method?: string | null;
  impedance_ohm?: number | null;
  impedance_angle_deg?: number | null;
  duration_ms?: number | null;
  confidence?: number | null;
  confidence_level?: ConfidenceLevel | null;
  explanation?: string | null;
  features?: Record<string, unknown> | null;
  is_primary: boolean;
}

export interface FaultLocationRow {
  algorithm: string;
  status: string;
  distance_km?: number | null;
  distance_pct?: number | null;
  unit: string;
  notes: string;
}

export interface FaultCharacteristics {
  event_id: string;
  fault_type: string;
  status: string;
  confidence_level?: string | null;
  involved_phases?: string[] | null;
  ground_involved?: boolean | null;
  distance_km?: number | null;
  location_method?: string | null;
  distance_applicable?: boolean | null;
  inception_t_us?: number | null;
  pickup_t_us?: number | null;
  trip_t_us?: number | null;
  clearing_t_us?: number | null;
  currents?: Record<string, unknown> | null;
  sequences?: Record<string, unknown> | null;
  current_unit?: string | null;
  impedance?: Record<string, unknown> | null;
  location_algorithms: FaultLocationRow[];
  line_impedance_estimate?: Record<string, unknown> | null;
  limitations: string[];
  explanation?: string | null;
}

export interface RcaHypothesis {
  id: string;
  event_id: string;
  hypothesis_code?: string | null;
  title: string;
  statement: string;
  status: HypothesisStatus;
  rank: number;
  confidence?: number | null;
  confidence_level?: ConfidenceLevel | null;
  supporting_evidence_ids?: string[] | null;
  contradicting_evidence_ids?: string[] | null;
  causal_chain?: string[] | null;
  recommended_actions?: string[] | null;
  explanation?: string | null;
  missing_evidence?: string[] | null;
  extra?: Record<string, unknown> | null;
}

export interface EvidenceItem {
  id: string;
  event_id: string;
  hypothesis_id?: string | null;
  evidence_key: string;
  source_type: string;
  polarity: 'SUPPORTING' | 'CONTRADICTING' | 'NEUTRAL' | 'MISSING';
  title: string;
  summary?: string | null;
  confidence?: number | null;
  t_us?: number | null;
  references?: Record<string, unknown> | null;
  children?: EvidenceItem[];
}

export interface Report {
  id: string;
  event_id: string;
  report_type: string;
  title: string;
  status: string;
  format?: string | null;
  summary?: string | null;
  html_content?: string | null;
  sections?: Record<string, unknown> | null;
  storage_key?: string | null;
  generated_at?: string | null;
}

export interface EngineerReview {
  id?: string;
  event_id: string;
  reviewer_id?: string | null;
  action: ReviewAction;
  decision_state?: DecisionState | null;
  comments?: string | null;
  modifications?: Record<string, unknown> | null;
  reviewed_at?: string | null;
}

export interface AnalysisStage {
  name: JobStage;
  label: string;
  status: StageStatus;
  message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface AnalysisJob {
  id: string;
  event_id: string;
  status: 'PENDING' | 'RUNNING' | 'COMPLETED' | 'FAILED' | 'CANCELLED';
  stage: JobStage;
  progress: number;
  stages: AnalysisStage[];
  current_message?: string | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  component_versions?: Record<string, string> | null;
}

export interface DashboardTrendPoint {
  date: string;
  events?: number;
  analysed: number;
  review: number;
  issues: number;
}

export interface DashboardDqBreakdown {
  good: number;
  acceptable: number;
  warning: number;
  poor: number;
  invalid: number;
  unknown: number;
  not_validated?: number;
  unsupported?: number;
}

export interface DashboardAttentionItem {
  id: string;
  event_id: string;
  reason: string;
  severity: string;
  href_status?: string;
}

export interface DashboardRecentEvent {
  id: string;
  event_id: string;
  event_datetime?: string | null;
  location: string;
  relay: string;
  fault_type?: string | null;
  protection_summary: string;
  consistency_summary: string;
  rca_status: string;
  severity?: string | null;
  status: string;
  data_quality?: string | null;
}

export interface DashboardStats {
  total_events: number;
  awaiting_analysis: number;
  awaiting_review: number;
  completed_reports: number;
  consistency_issues: number;
  high_severity_findings: number;
  rca_inconclusive: number;
  parser_dq_issues: number;
  trend_30d?: DashboardTrendPoint[];
  data_quality?: DashboardDqBreakdown;
  attention?: DashboardAttentionItem[];
  recent_events?: DashboardRecentEvent[];
}

export interface SettingVersion {
  id: string;
  relay_id: string;
  version_label: string;
  version_number: number;
  source?: string | null;
  approval_status: string;
  effective_from?: string | null;
  checksum_sha256?: string | null;
}

export interface SettingGroup {
  id: string;
  relay_id: string;
  group_number: number;
  name: string;
  is_active: boolean;
}

export interface RuleVersion {
  id: string;
  rule_family: string;
  version: string;
  name: string;
  is_active: boolean;
  description?: string | null;
}

export interface ModelVersion {
  id: string;
  model_name: string;
  version: string;
  model_type?: string | null;
  is_active: boolean;
  framework?: string | null;
  metrics?: Record<string, number> | null;
}

export interface AuditLogEntry {
  id: string;
  user_id?: string | null;
  username?: string | null;
  timestamp: string;
  action: string;
  object_type?: string | null;
  object_id?: string | null;
  ip_address?: string | null;
}

export interface SettingSourceInfo {
  source: string;
  version: string;
  approval_status?: string;
  group?: string;
  active_group_status?: string;
  verification_state?: string;
  effective_from?: string | null;
  relay_tag?: string | null;
  checksum?: string | null;
}
