import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import { api } from '@/services/api';
import type {
  ConsistencyFinding,
  FaultClassification,
  ProtectionOperation,
  RcaHypothesis,
  SettingSourceInfo,
  TimelineEntry,
} from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { SettingSourceBanner } from '@/components/SettingSourceBanner';
import { VerifyActiveSettingsCard } from '@/components/VerifyActiveSettingsCard';
import { OneLineBay } from '@/components/OneLineBay';
import {
  formatOperatedElements,
  filterDistanceLimitations,
  resolveBaySchemeHint,
  resolveDistanceApplicable,
  resolveFaultType,
} from '@/utils/schemeContext';
import { formatAnsiCompact } from '@/utils/ansiDeviceNames';
import { isEvidenceBackedAssert } from '@/utils/protectionOperateEvidence';
import {
  eventClassFromFault,
  groundInvolvedLabel,
  humanizeEventClass,
  humanizeEvidenceToken,
  humanizeFaultType,
  isShuntFaultEventClass,
} from '@/utils/evidenceLabels';
import { formatCheckName } from '@/utils/findingValue';
import styles from './EventOverviewPage.module.css';

const SETTING_SOURCE_LABELS: Record<string, string> = {
  APPROVED_RELAY_BASE: 'Approved relay base',
  APPROVED_RELAY_BASE_SETTINGS: 'Approved relay base',
  RELAY_CONFIGURATION: 'Relay configuration',
  EVENT_SPECIFIC_ACTIVE: 'Event-specific active settings',
  ACTIVE_SETTING_GROUP: 'Active setting group',
  HISTORICAL: 'Historical settings',
  ENGINEERING_DESIGN: 'Engineering design settings',
  UPLOADED: 'Uploaded package',
  NOT_VERIFIED: 'Not verified',
  'NOT VERIFIED': 'Not verified',
  'NOT AVAILABLE': 'Not available',
};

function settingLabel(raw: string | null | undefined): string {
  if (!raw) return 'Not verified';
  if (SETTING_SOURCE_LABELS[raw]) return SETTING_SOURCE_LABELS[raw];
  if (SETTING_SOURCE_LABELS[raw.toUpperCase()]) return SETTING_SOURCE_LABELS[raw.toUpperCase()];
  return raw.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function timelineLabel(eventType: string | undefined): string {
  if (!eventType) return 'Event';
  const u = eventType.toUpperCase();
  if (u.includes('INCEPTION')) return 'Fault inception';
  if (u.includes('PICKUP')) return 'Pickup';
  if (u.includes('TRIP')) return 'Trip';
  return formatCheckName(eventType);
}

const OPTIONAL_INPUTS = new Set(['SOE', 'Event report', 'Ends']);

type InputChip = {
  summary: string;
  detail: string;
  ok: boolean;
  missing: boolean;
};

function formatInputChip(label: string, val: unknown): InputChip {
  const optional = OPTIONAL_INPUTS.has(label);

  if (val == null || val === '' || val === '—') {
    return {
      summary: optional ? 'Not uploaded (optional)' : 'Not loaded',
      detail: optional
        ? `${label} is optional — upload SOE CSV or relay event report if available.`
        : `${label} was not loaded for this event.`,
      ok: false,
      missing: true,
    };
  }

  if (typeof val === 'object') {
    const o = val as Record<string, unknown>;
    const file = o.file ?? o.filename ?? o.name;
    const events = o.events ?? o.n ?? o.count;
    const note = o.note != null ? String(o.note) : '';
    const n = typeof events === 'number' ? events : Number(events);
    const parts: string[] = [];
    if (file) parts.push(String(file));
    if (Number.isFinite(n)) {
      parts.push(n === 1 ? '1 event' : `${n} events`);
    }
    if (!parts.length && note) parts.push(note);
    const summary = parts.length ? parts.join(' · ') : 'Loaded';
    const detail = [summary, note].filter(Boolean).join(' — ');
    const ok = (Number.isFinite(n) && n > 0) || Boolean(file);
    return { summary, detail: detail || summary, ok, missing: !ok };
  }

  const raw = String(val).trim();
  const upper = raw.toUpperCase();

  if (/NOT\s*LOADED|MISSING|NO_SAMPLES/.test(upper)) {
    if (upper.includes('NO_SAMPLES')) {
      return {
        summary: 'No samples',
        detail: 'COMTRADE parsed but sample data is missing.',
        ok: false,
        missing: true,
      };
    }
    return {
      summary: optional ? 'Not uploaded (optional)' : 'Not loaded',
      detail: optional
        ? `${label} is optional — upload if available for richer timeline evidence.`
        : raw,
      ok: false,
      missing: true,
    };
  }

  if (/^(OK|LOADED)$/i.test(raw)) {
    return { summary: 'OK', detail: `${label}: OK`, ok: true, missing: false };
  }

  // Settings: "relay_settings.json (6 params)"
  const settingsMatch = raw.match(/^(.+?)\s*\((\d+)\s*params?\)$/i);
  if (settingsMatch) {
    const n = Number(settingsMatch[2]);
    return {
      summary: `${settingsMatch[1]} · ${n} parameter${n === 1 ? '' : 's'}`,
      detail: raw,
      ok: n > 0,
      missing: n <= 0,
    };
  }

  if (/\d+\s*params?/i.test(raw) || /\d+\s*events?/i.test(raw)) {
    return { summary: raw, detail: raw, ok: true, missing: false };
  }

  return {
    summary: raw,
    detail: raw,
    ok: /^(OK|LOADED)/i.test(raw),
    missing: false,
  };
}

function formatMs(tUs: number | null | undefined, absolute?: string | null): string {
  if (absolute) return absolute;
  if (tUs == null) return '—';
  return `${(tUs / 1000).toFixed(1)} ms`;
}

function notCalc(v: unknown, label = 'NOT CALCULABLE'): string {
  if (v == null || v === '' || v === undefined) return label;
  if (typeof v === 'number' && Number.isFinite(v)) {
    return Math.abs(v) >= 100 ? v.toFixed(2) : v.toFixed(3);
  }
  return String(v);
}

function formatDistanceKm(km: number | null | undefined): string {
  if (km == null || Number.isNaN(Number(km))) return 'NOT CALCULABLE';
  const n = Number(km);
  if (Math.abs(n) >= 10) return `${n.toFixed(3)} km`;
  return `${n.toFixed(4)} km`;
}

function faultLoopZ(fault: FaultClassification | null): {
  mag: number | null;
  ang: number | null;
} {
  if (!fault) return { mag: null, ang: null };
  if (fault.impedance_ohm != null) {
    return { mag: fault.impedance_ohm, ang: fault.impedance_angle_deg ?? null };
  }
  const feat = fault.features as
    | { loop_impedance?: { magnitude_ohm?: number; angle_deg?: number } }
    | null
    | undefined;
  const loop = feat?.loop_impedance;
  if (loop?.magnitude_ohm != null) {
    return { mag: loop.magnitude_ohm, ang: loop.angle_deg ?? null };
  }
  return { mag: null, ang: null };
}

export function EventOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { event, reload, analysisRevision } = useEventOrWorkspace(id);
  const [fault, setFault] = useState<FaultClassification | null>(null);
  const [rca, setRca] = useState<RcaHypothesis[]>([]);
  const [protection, setProtection] = useState<ProtectionOperation[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [findings, setFindings] = useState<ConsistencyFinding[]>([]);
  const [overallCons, setOverallCons] = useState('NOT_AVAILABLE');
  const [settingSource, setSettingSource] = useState<SettingSourceInfo | null>(null);
  const [station, setStation] = useState<string | null>(null);
  const [device, setDevice] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    void api
      .getFaultClassification(id)
      .then((f) => {
        if (Array.isArray(f)) setFault(f[0] ?? null);
        else setFault(f);
      })
      .catch(() => setFault(null));
    void api.getRca(id).then((r) => setRca(r.hypotheses)).catch(() => setRca([]));
    void api.getProtection(id).then(setProtection).catch(() => setProtection([]));
    void api.getTimeline(id).then(setTimeline).catch(() => setTimeline([]));
    void api.getConsistency(id).then((r) => {
      setFindings(r.findings);
      setOverallCons(r.overall_status);
      setSettingSource(r.setting_source);
    });
    void api
      .getComtrade(id)
      .then((ct) => {
        setStation(ct.station_name ?? null);
        setDevice(ct.recording_device ?? null);
      })
      .catch(() => {
        setStation(null);
        setDevice(null);
      });
  }, [id, analysisRevision]);

  const primary = rca.find((h) => h.rank === 1) ?? rca[0];
  const missingFromExtra =
    (primary?.extra as { missing_evidence?: string[] } | undefined)?.missing_evidence ??
    primary?.missing_evidence ??
    [];
  const inception =
    timeline.find((t) => (t.event_type || '').toUpperCase().includes('INCEPTION')) ??
    timeline.find((t) => {
      const et = (t.event_type || '').toUpperCase();
      return et === 'FAULT_INCEPTION' || et.startsWith('FAULT_');
    });
  const trips = protection.filter(
    (p) =>
      isEvidenceBackedAssert(p) &&
      (p.operation_type || '').toUpperCase().includes('TRIP'),
  );
  const plantExtraEarly = (event?.extra as Record<string, unknown> | undefined) ?? {};
  const fileProcessingEarly =
    (plantExtraEarly.file_processing as Record<string, unknown> | undefined) ?? null;
  const ctVtStatus = String(fileProcessingEarly?.ct_vt ?? '').toUpperCase();
  const lineStatus = String(fileProcessingEarly?.line_params ?? '').toUpperCase();

  const uncertain: string[] = [];
  if ((settingSource?.active_group_status || settingSource?.verification_state) === 'NOT VERIFIED') {
    uncertain.push('Active setting group: NOT VERIFIED');
  }
  if (!event?.data_quality || event.data_quality === 'WARNING' || event.data_quality === 'POOR') {
    if (event?.data_quality) uncertain.push(`Data quality: ${event.data_quality}`);
  }
  if (missingFromExtra.length) {
    uncertain.push(...missingFromExtra);
  }
  if (overallCons === 'INCONSISTENT') {
    uncertain.push(
      'Protection consistency has INCONSISTENT findings — do not confirm relay malfunction from this alone',
    );
  }
  const distanceContext = resolveDistanceApplicable({
    fault,
    protection,
    eventExtra: (event?.extra || {}) as Record<string, unknown>,
  });
  if (distanceContext && fault?.distance_km == null) {
    const need: string[] = [];
    if (lineStatus !== 'OK') need.push('verified line parameters (Z1/Z0, length)');
    if (ctVtStatus !== 'OK') need.push('CT/VT ratios in settings JSON');
    if (!need.length) {
      need.push('validated loop impedance / polarity check (line + CT/VT were loaded but km still not calculable)');
    }
    uncertain.push(`Fault location (km): NOT CALCULABLE — need ${need.join(' and ')}`);
  }

  const verifyActions =
    primary?.recommended_actions?.length
      ? primary.recommended_actions
      : [
          'Verify active relay setting group',
          'Verify relay configuration / channel mapping',
          'Review COMTRADE validation warnings',
          'Confirm breaker timing from SOE if available',
        ];

  const plantExtra = (event?.extra as Record<string, string> | undefined) ?? {};
  const fileProcessing = (
    event?.extra as { file_processing?: Record<string, unknown> } | undefined
  )?.file_processing;
  const substation = event?.substation_name ?? station ?? 'UNKNOWN';
  const bay = event?.bay_name ?? 'NOT VERIFIED';
  const relay = event?.relay_tag ?? device ?? 'NOT VERIFIED';
  const feederLabel = event?.feeder ?? null;

  return (
    <div>
      {settingSource && (
        <SettingSourceBanner source={settingSource} />
      )}

      {event && id && (
        <OneLineBay
          substation={substation}
          bay={bay}
          relay={relay}
          feeder={feederLabel}
          faultType={resolveFaultType({
            fault,
            eventFaultType: event.fault_type,
            eventExtra: (event.extra || {}) as Record<string, unknown>,
          })}
          distanceKm={distanceContext ? fault?.distance_km : null}
          distanceApplicable={distanceContext}
          schemeHint={resolveBaySchemeHint({
            protection,
            eventExtra: (event.extra || {}) as Record<string, unknown>,
          })}
          onOpenDr={() => navigate(`/events/${id}/dr`)}
        />
      )}

      {id && (
        <VerifyActiveSettingsCard
          eventId={id}
          source={settingSource}
          settingsLoaded={Boolean(
            plantExtra.setting_source ||
              plantExtra.setting_param_count ||
              plantExtra.setting_group ||
              (event?.extra as { settings_file_verification_note?: string } | undefined)
                ?.settings_file_verification_note,
          )}
          fileNote={
            (event?.extra as { settings_file_verification_note?: string } | undefined)
              ?.settings_file_verification_note
          }
          onVerified={() => {
            void reload();
            void api.getConsistency(id).then((r) => {
              setFindings(r.findings);
              setOverallCons(r.overall_status);
              setSettingSource(r.setting_source);
            });
          }}
        />
      )}

      {fileProcessing && (
        <div className={`alert alert-info ${styles.files}`}>
          <strong>Inputs loaded</strong>
          <div className={styles.chipRow}>
            {(
              [
                ['COMTRADE', fileProcessing.comtrade],
                ['Settings', fileProcessing.settings],
                ['SOE', fileProcessing.soe],
                ['Event report', fileProcessing.event_report],
                ['Line params', fileProcessing.line_params],
                ['CT/VT', fileProcessing.ct_vt],
                ...(fileProcessing.ends
                  ? ([['Ends', fileProcessing.ends]] as Array<[string, unknown]>)
                  : []),
              ] as Array<[string, unknown]>
            ).map(([label, val]) => {
              const chip = formatInputChip(label, val);
              return (
                <span
                  key={label}
                  className={`${styles.chip} ${chip.ok ? styles.chipOk : ''} ${chip.missing ? styles.chipWarn : ''}`}
                  title={chip.detail}
                >
                  <span className={styles.chipLabel}>{label}</span>
                  <span className={styles.chipValue}>{chip.summary}</span>
                </span>
              );
            })}
          </div>
        </div>
      )}

      <div className={styles.brief}>
        <section className={styles.card}>
          <div className={styles.label}>What happened</div>
          <div className={styles.rows}>
            <div className={styles.row}>
              <span className={styles.rowKey}>Event class</span>
              <span className={styles.rowVal}>
                {humanizeEventClass(eventClassFromFault(fault))}
              </span>
            </div>
            <div className={styles.row}>
              <span className={styles.rowKey}>Fault</span>
              <span className={styles.rowVal}>
                {humanizeFaultType(
                  resolveFaultType({
                    fault,
                    eventFaultType: event?.fault_type,
                    eventExtra: (event?.extra || {}) as Record<string, unknown>,
                  }),
                  eventClassFromFault(fault),
                )}
                {fault?.status && isShuntFaultEventClass(eventClassFromFault(fault)) ? (
                  <>
                    {' '}
                    <StatusBadge status={fault.status} />
                  </>
                ) : null}
              </span>
            </div>
            {(inception?.absolute_time || inception?.t_us != null) && (
              <div className={styles.row}>
                <span className={styles.rowKey}>Start</span>
                <span className={styles.rowVal}>
                  {timelineLabel(inception.event_type)} @{' '}
                  {formatMs(inception.t_us, inception.absolute_time)}
                </span>
              </div>
            )}
            <div className={styles.row}>
              <span className={styles.rowKey}>Operated</span>
              <span className={styles.rowVal}>
                {trips.length
                  ? trips.map((t) => formatAnsiCompact(t.element)).join(' · ') + ' trip'
                  : formatOperatedElements(protection) || 'None asserted'}
              </span>
            </div>
            <div className={styles.row}>
              <span className={styles.rowKey}>Check</span>
              <span className={styles.rowVal}>
                <StatusBadge status={overallCons} />
                <span className={styles.muted}> · {findings.length} finding{findings.length === 1 ? '' : 's'}</span>
              </span>
            </div>
            <div className={styles.row}>
              <span className={styles.rowKey}>Quality</span>
              <span className={styles.rowVal}>
                {event?.data_quality ? (
                  <StatusBadge status={event.data_quality} />
                ) : (
                  'Not validated'
                )}
              </span>
            </div>
          </div>
        </section>

        <section className={`${styles.card} ${styles.cardWhy}`}>
          <div className={styles.label}>Why (evidence-linked)</div>
          {primary ? (
            <>
              <div className={styles.headline}>
                {primary.title}
                <StatusBadge status={primary.status} />
              </div>
              {primary.statement && (
                <p className={styles.muted} style={{ margin: 0 }}>
                  {primary.statement.length > 140
                    ? `${primary.statement.slice(0, 140)}…`
                    : primary.statement}
                </p>
              )}
              <div className={styles.actions}>
                <Link className={styles.linkBtn} to={`/events/${id}/rca`}>
                  Open RCA
                </Link>
                <Link className={styles.linkBtn} to={`/events/${id}/evidence`}>
                  Evidence
                </Link>
              </div>
            </>
          ) : (
            <p className={styles.muted} style={{ margin: 0 }}>
              RCA pending — re-run analysis after upload
            </p>
          )}
        </section>

        <section className={`${styles.card} ${styles.cardSettings}`}>
          <div className={styles.label}>Which setting</div>
          <div className={styles.rows}>
            <div className={styles.row}>
              <span className={styles.rowKey}>Source</span>
              <span className={styles.rowVal}>{settingLabel(settingSource?.source)}</span>
            </div>
            <div className={styles.row}>
              <span className={styles.rowKey}>Version</span>
              <span className={styles.rowVal}>{settingLabel(settingSource?.version)}</span>
            </div>
            <div className={styles.row}>
              <span className={styles.rowKey}>Group</span>
              <span className={styles.rowVal}>{settingSource?.group || '—'}</span>
            </div>
            <div className={styles.row}>
              <span className={styles.rowKey}>Active</span>
              <span className={styles.rowVal}>
                <StatusBadge
                  status={
                    settingSource?.active_group_status ??
                    settingSource?.verification_state ??
                    'NOT VERIFIED'
                  }
                />
              </span>
            </div>
          </div>
        </section>

        <section className={`${styles.card} ${styles.cardUncertain}`}>
          <div className={styles.label}>What is uncertain</div>
          {uncertain.length ? (
            <ul className={`${styles.list} ${styles.listWarn}`}>
              {uncertain.slice(0, 5).map((u) => (
                <li key={u}>{humanizeEvidenceToken(u)}</li>
              ))}
            </ul>
          ) : (
            <p className={styles.muted} style={{ margin: 0 }}>
              No open uncertainty flags from the current analysis
            </p>
          )}
        </section>

        <section className={`${styles.card} ${styles.cardVerify}`}>
          <div className={styles.label}>What should I verify</div>
          <ul className={styles.list}>
            {verifyActions.slice(0, 4).map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
          {id && (
            <div className={styles.actions}>
              <Link className={styles.linkBtn} to={`/events/${id}/review`}>
                Go to review
              </Link>
            </div>
          )}
        </section>
      </div>

      <div className="two-col stack-md">
        <div className="panel">
          <div className="panel-header">Event summary</div>
          <div className="panel-body">
            <table className="data-table">
              <tbody>
                <tr>
                  <td>Substation / Bay</td>
                  <td>
                    {substation} / {bay}
                  </td>
                </tr>
                <tr>
                  <td>Relay / device</td>
                  <td className="mono">{relay}</td>
                </tr>
                <tr>
                  <td>Description</td>
                  <td>{event?.description?.trim() ? event.description : '—'}</td>
                </tr>
                <tr>
                  <td>Nominal</td>
                  <td className="num">
                    {event?.nominal_voltage_kv != null
                      ? event.nominal_voltage_kv
                      : (() => {
                          const vl =
                            (plantExtra.voltage_level_name as string | undefined) || '';
                          const m = vl.match(/([0-9]{1,3}(?:\.[0-9]+)?)\s*k\s*v/i);
                          return m ? m[1] : 'UNKNOWN';
                        })()}{' '}
                    kV / {event?.nominal_frequency_hz ?? 50} Hz
                  </td>
                </tr>
                <tr>
                  <td>Decision</td>
                  <td>
                    {event?.decision_state ? (
                      <StatusBadge status={event.decision_state} />
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
                <tr>
                  <td>Consistency findings</td>
                  <td className="mono">
                    {findings.filter((f) => f.status === 'INCONSISTENT').length} inconsistent /{' '}
                    {findings.length} total
                  </td>
                </tr>
              </tbody>
            </table>
            <div style={{ marginTop: 12, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <Link className="btn btn-sm btn-primary" to={`/events/${id}/summary`}>
                Printable summary
              </Link>
              <Link className="btn btn-sm" to={`/events/${id}/waveforms`}>
                Waveforms
              </Link>
              <Link className="btn btn-sm" to={`/events/${id}/electrical`}>
                Phasors
              </Link>
              <Link className="btn btn-sm" to={`/events/${id}/consistency`}>
                Consistency
              </Link>
              <Link className="btn btn-sm" to={`/events/${id}/rca`}>
                RCA
              </Link>
              <Link className="btn btn-sm" to={`/events/${id}/review`}>
                Engineer review
              </Link>
            </div>
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">Fault classification</div>
          <div className="panel-body">
            {fault ? (
              <>
                <div className="badge-row" style={{ marginBottom: 12 }}>
                  <span className="mono" style={{ fontSize: '1.4rem', fontWeight: 700 }}>
                    {humanizeFaultType(fault.fault_type, eventClassFromFault(fault))}
                  </span>
                  {isShuntFaultEventClass(eventClassFromFault(fault)) ? (
                    <StatusBadge status={fault.status} />
                  ) : null}
                </div>
                <table className="data-table">
                  <tbody>
                    <tr>
                      <td>Phases</td>
                      <td className="mono">
                        {isShuntFaultEventClass(eventClassFromFault(fault))
                          ? fault.involved_phases?.join(', ') ?? '—'
                          : '—'}
                      </td>
                    </tr>
                    <tr>
                      <td>Ground</td>
                      <td>
                        {(() => {
                          const g = groundInvolvedLabel(
                            eventClassFromFault(fault),
                            fault.ground_involved,
                          );
                          return g === '—' ? 'NOT AVAILABLE' : g;
                        })()}
                      </td>
                    </tr>
                    {distanceContext && (
                      <>
                        <tr>
                          <td>Location (km)</td>
                          <td className="num">{formatDistanceKm(fault.distance_km)}</td>
                        </tr>
                        <tr>
                          <td>Loop Z</td>
                          <td className="num">
                            {(() => {
                              const z = faultLoopZ(fault);
                              if (z.mag == null) {
                                return <>NOT CALCULABLE Ω ∠ —°</>;
                              }
                              return (
                                <>
                                  {notCalc(z.mag)} Ω ∠ {notCalc(z.ang, '—')}°
                                </>
                              );
                            })()}
                          </td>
                        </tr>
                      </>
                    )}
                    {!distanceContext && (
                      <tr>
                        <td>Location / Z</td>
                        <td style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
                          Not applicable (no distance operate/backup or line-location inputs for this scheme).
                          See Protection and Electrical tabs.
                        </td>
                      </tr>
                    )}
                    <tr>
                      <td>Confidence</td>
                      <td className="num">
                        {fault.confidence_level} (
                        {((fault.confidence ?? 0) * 100).toFixed(0)}%)
                      </td>
                    </tr>
                  </tbody>
                </table>
                {(() => {
                  const note = filterDistanceLimitations(fault.explanation, distanceContext);
                  return note ? (
                    <p style={{ marginTop: 12, color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
                      {note}
                    </p>
                  ) : null;
                })()}
              </>
            ) : (
              <div className="empty-state">
                Classification pending — use <strong>Re-run analysis</strong> after upload
              </div>
            )}
          </div>
        </div>
      </div>

      {primary && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">Primary RCA hypothesis</div>
          <div className="panel-body">
            <div className="badge-row" style={{ marginBottom: 8 }}>
              <StatusBadge status={primary.status} />
              {primary.hypothesis_code && (
                <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  {primary.hypothesis_code.replace(/_/g, ' ').toLowerCase()}
                </span>
              )}
            </div>
            <h3 style={{ margin: '0 0 8px' }}>{primary.title}</h3>
            <p style={{ margin: 0, color: 'var(--text-secondary)' }}>{primary.statement}</p>
            {missingFromExtra.length > 0 && (
              <div className="alert alert-info" style={{ marginTop: 12 }}>
                Missing evidence for full confirmation:{' '}
                {missingFromExtra.map(humanizeEvidenceToken).join('; ')}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
