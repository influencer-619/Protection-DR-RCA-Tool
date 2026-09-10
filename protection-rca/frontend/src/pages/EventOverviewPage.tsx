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
import { PlantLabelsEditor } from '@/components/PlantLabelsEditor';
import { OneLineBay } from '@/components/OneLineBay';
import { formatOperatedElements, filterDistanceLimitations, isDistanceApplicable } from '@/utils/schemeContext';
import { humanizeEvidenceToken } from '@/utils/evidenceLabels';

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
  const { event, reload, applyEvent, analysisRevision } = useEventOrWorkspace(id);
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
    void api.getRca(id).then(setRca).catch(() => setRca([]));
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
  const inception = timeline.find((t) => {
    const et = (t.event_type || '').toUpperCase();
    return et.includes('INCEPTION') || et.includes('FAULT') || et.includes('PICKUP');
  });
  const trips = protection.filter(
    (p) => p.asserted && (p.operation_type || '').toUpperCase().includes('TRIP'),
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
  const distanceContext = isDistanceApplicable({ fault, protection });
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
  const plantLabels =
    (event?.extra as { plant_labels?: Record<string, string> } | undefined)?.plant_labels ?? {};
  const fileProcessing = (
    event?.extra as { file_processing?: Record<string, unknown> } | undefined
  )?.file_processing;
  const substation =
    event?.substation_name ??
    plantLabels.substation_name ??
    plantExtra.substation_name ??
    station ??
    'UNKNOWN';
  const bay = event?.bay_name ?? plantLabels.bay_name ?? plantExtra.bay_name ?? 'NOT VERIFIED';
  const relay =
    event?.relay_tag ?? plantLabels.relay_tag ?? plantExtra.relay_tag ?? device ?? 'NOT VERIFIED';

  return (
    <div>
      {settingSource && <SettingSourceBanner source={settingSource} />}

      {event && (
        <PlantLabelsEditor
          event={event}
          onSaved={(updated) => {
            applyEvent(updated);
            void reload();
          }}
        />
      )}

      {event && id && (
        <OneLineBay
          substation={event.substation_name || (plantExtra.substation_name as string)}
          bay={event.bay_name || (plantExtra.bay_name as string)}
          relay={event.relay_tag || (plantExtra.relay_tag as string)}
          feeder={event.feeder}
          faultType={event.fault_type}
          distanceKm={distanceContext ? fault?.distance_km : null}
          distanceApplicable={distanceContext}
          schemeHint={
            protection.find((p) => p.asserted && /\b87/i.test(`${p.element} ${p.function_code}`))
              ?.element || null
          }
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
        <div className="alert alert-info" style={{ marginBottom: 12 }}>
          <strong>File processing:</strong>{' '}
          {[
            `COMTRADE=${String(fileProcessing.comtrade ?? '—')}`,
            `Settings=${typeof fileProcessing.settings === 'object' ? JSON.stringify(fileProcessing.settings) : String(fileProcessing.settings ?? '—')}`,
            `SOE=${typeof fileProcessing.soe === 'object' ? JSON.stringify(fileProcessing.soe) : String(fileProcessing.soe ?? '—')}`,
            `Event report=${typeof fileProcessing.event_report === 'object' ? JSON.stringify(fileProcessing.event_report) : String(fileProcessing.event_report ?? '—')}`,
            `Line=${String(fileProcessing.line_params ?? '—')}`,
            `CT/VT=${String(fileProcessing.ct_vt ?? '—')}`,
          ].join(' · ')}
        </div>
      )}

      <div className="ux-strip">
        <div className="ux-item">
          <div className="ux-label">What happened</div>
          <div className="ux-value">
            Fault: {fault?.fault_type ?? 'UNKNOWN'}
            {fault?.status ? ` (${fault.status})` : ''}
            {inception?.absolute_time || inception?.t_us != null
              ? ` · ${inception.event_type} @ ${
                  inception.absolute_time ?? `${((inception.t_us ?? 0) / 1000).toFixed(1)} ms`
                }`
              : ''}
            <br />
            Operated:{' '}
            {trips.length
              ? trips.map((t) => `${t.element} ${t.operation_type}`).join(', ')
              : formatOperatedElements(protection)}
            <br />
            Consistency: {overallCons} · Findings: {findings.length}
            <br />
            DQ: {event?.data_quality ?? 'NOT VALIDATED'}
          </div>
        </div>
        <div className="ux-item">
          <div className="ux-label">Why (evidence-linked)</div>
          <div className="ux-value">
            {primary ? (
              <>
                {primary.title} · {primary.status}
                <div style={{ marginTop: 6, fontSize: '0.8rem' }}>
                  <Link to={`/events/${id}/evidence`}>Open evidence graph</Link>
                  {' · '}
                  <Link to={`/events/${id}/rca`}>RCA detail</Link>
                </div>
              </>
            ) : (
              'Pending RCA — click Re-run analysis after upload'
            )}
          </div>
        </div>
        <div className="ux-item">
          <div className="ux-label">Which setting</div>
          <div className="ux-value mono">
            Source: {settingSource?.source ?? 'NOT VERIFIED'}
            <br />
            Version: {settingSource?.version ?? 'NOT VERIFIED'}
            <br />
            Group: {settingSource?.group ?? 'NOT VERIFIED'}
            <br />
            Active group:{' '}
            {settingSource?.active_group_status ??
              settingSource?.verification_state ??
              'NOT VERIFIED'}
          </div>
        </div>
        <div className="ux-item">
          <div className="ux-label">What is uncertain</div>
          <div className={`ux-value ${uncertain.length ? 'uncertain' : ''}`}>
            {uncertain.length ? (
              <ul style={{ margin: 0, paddingLeft: 16 }}>
                {uncertain.slice(0, 5).map((u) => (
                  <li key={u}>{u}</li>
                ))}
              </ul>
            ) : (
              'No open uncertainty flags from current analysis'
            )}
          </div>
        </div>
        <div className="ux-item">
          <div className="ux-label">What should I verify</div>
          <div className="ux-value">
            <ul style={{ margin: 0, paddingLeft: 16 }}>
              {verifyActions.slice(0, 4).map((a) => (
                <li key={a}>{a}</li>
              ))}
            </ul>
          </div>
        </div>
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
                  <td>{event?.description ?? '—'}</td>
                </tr>
                <tr>
                  <td>Nominal</td>
                  <td className="num">
                    {event?.nominal_voltage_kv ?? 'UNKNOWN'} kV /{' '}
                    {event?.nominal_frequency_hz ?? 50} Hz
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
                    {fault.fault_type}
                  </span>
                  <StatusBadge status={fault.status} />
                </div>
                <table className="data-table">
                  <tbody>
                    <tr>
                      <td>Phases</td>
                      <td className="mono">{fault.involved_phases?.join(', ') ?? '—'}</td>
                    </tr>
                    <tr>
                      <td>Ground</td>
                      <td>
                        {fault.ground_involved == null
                          ? 'NOT AVAILABLE'
                          : fault.ground_involved
                            ? 'Yes'
                            : 'No'}
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
              <span className="mono">{primary.hypothesis_code}</span>
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
