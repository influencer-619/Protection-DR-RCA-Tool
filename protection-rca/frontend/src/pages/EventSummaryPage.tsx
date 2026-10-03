import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { format } from 'date-fns';
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
import { DataQualityBadge } from '@/components/DataQualityBadge';
import { EmptyState } from '@/components/EmptyState';
import { VerdictStrip } from '@/components/VerdictStrip';
import { SharePackButton } from '@/components/SharePackButton';
import { isDistanceApplicable } from '@/utils/schemeContext';
import { formatConfidencePct, humanizeEvidenceToken } from '@/utils/evidenceLabels';
import { formatCheckName } from '@/utils/findingValue';
import styles from './EventSummaryPage.module.css';

const SETTING_LABELS: Record<string, string> = {
  APPROVED_RELAY_BASE: 'Approved relay base',
  APPROVED_RELAY_BASE_SETTINGS: 'Approved relay base',
  RELAY_CONFIGURATION: 'Relay configuration',
  EVENT_SPECIFIC_ACTIVE: 'Event-specific active settings',
  ACTIVE_SETTING_GROUP: 'Active setting group',
  UPLOADED: 'Uploaded package',
  'NOT VERIFIED': 'Not verified',
  NOT_VERIFIED: 'Not verified',
  'NOT AVAILABLE': 'Not available',
};

function settingLabel(raw: string | null | undefined): string {
  if (!raw) return 'Not verified';
  return SETTING_LABELS[raw] || SETTING_LABELS[raw.toUpperCase()] || raw.replace(/_/g, ' ');
}

function timelineLabel(t: TimelineEntry): string {
  const raw = (t.label || t.event_type || '').trim();
  if (!raw) return 'Event';
  if (/\s/.test(raw) && /[a-z]/.test(raw)) return raw;
  const u = raw.toUpperCase();
  if (u.includes('INCEPTION') && u.includes('FAULT')) return 'Fault inception';
  if (u === 'FAULT_INCEPTION') return 'Fault inception';
  if (u === 'CURRENT_INCREASE') return 'Current increase';
  if (u === 'VOLTAGE_CHANGE') return 'Voltage change';
  if (u === 'PROTECTION_PICKUP') return 'Protection pickup';
  if (u === 'PROTECTION_TRIP') return 'Protection trip';
  if (u === '52A_CHANGE') return 'Breaker auxiliary (52a)';
  if (u === 'CURRENT_INTERRUPTION') return 'Current interruption';
  return formatCheckName(raw);
}

function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return format(d, 'dd MMM yyyy HH:mm:ss');
}

function fmtDistance(km: number | null | undefined): string {
  if (km == null || Number.isNaN(Number(km))) return 'Not calculable';
  const n = Number(km);
  return `${n >= 10 ? n.toFixed(2) : n.toFixed(3)} km`;
}

function looksLikeFileBatch(desc: string | null | undefined): boolean {
  if (!desc) return true;
  if (/^upload batch/i.test(desc)) return true;
  const hits = ['.cfg', '.dat', '.json', '.txt', '.csv'].filter((e) =>
    desc.toLowerCase().includes(e),
  ).length;
  return hits >= 2;
}

export function EventSummaryPage() {
  const { id } = useParams<{ id: string }>();
  const { event, loading: eventLoading, analysisRevision } = useEventOrWorkspace(id);
  const [fault, setFault] = useState<FaultClassification | null>(null);
  const [rca, setRca] = useState<RcaHypothesis[]>([]);
  const [protection, setProtection] = useState<ProtectionOperation[]>([]);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [findings, setFindings] = useState<ConsistencyFinding[]>([]);
  const [overallCons, setOverallCons] = useState('NOT_AVAILABLE');
  const [settingSource, setSettingSource] = useState<SettingSourceInfo | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (!id) return;
    setLoaded(false);
    Promise.all([
      api
        .getFaultClassification(id)
        .then((f) => {
          if (Array.isArray(f)) setFault(f[0] ?? null);
          else setFault(f);
        })
        .catch(() => setFault(null)),
      api.getRca(id).then(setRca).catch(() => setRca([])),
      api.getProtection(id).then(setProtection).catch(() => setProtection([])),
      api.getTimeline(id).then(setTimeline).catch(() => setTimeline([])),
      api.getConsistency(id).then((r) => {
        setFindings(r.findings);
        setOverallCons(r.overall_status);
        setSettingSource(r.setting_source);
      }),
    ]).finally(() => setLoaded(true));
  }, [id, analysisRevision]);

  const primary = rca.find((h) => h.rank === 1) ?? rca[0];
  const trips = protection.filter(
    (p) => p.asserted && (p.operation_type || '').toUpperCase().includes('TRIP'),
  );
  const pickups = protection.filter(
    (p) => p.asserted && (p.operation_type || '').toUpperCase().includes('PICKUP'),
  );
  const inconsistent = findings.filter((f) => f.status === 'INCONSISTENT');
  const plantExtra = (event?.extra as Record<string, string> | undefined) ?? {};
  const plantLabels =
    (event?.extra as { plant_labels?: Record<string, string> } | undefined)?.plant_labels ?? {};

  const substation =
    event?.substation_name ?? plantLabels.substation_name ?? plantExtra.substation_name ?? '—';
  const bay = event?.bay_name ?? plantLabels.bay_name ?? plantExtra.bay_name ?? '—';
  const relay = event?.relay_tag ?? plantLabels.relay_tag ?? plantExtra.relay_tag ?? '—';

  const timing = useMemo(() => {
    const byType = new Map<string, number>();
    for (const t of timeline) {
      const key = (t.event_type || '').toLowerCase();
      if (!key || t.t_us == null || byType.has(key)) continue;
      byType.set(key, t.t_us / 1000);
    }
    const pickup = byType.get('protection_pickup');
    const trip = byType.get('protection_trip');
    const interrupt = byType.get('current_interruption');
    const breaker = byType.get('52a_change');
    // Values are already in milliseconds (t_us / 1000).
    return {
      pickupToTripMs:
        pickup != null && trip != null ? Math.round((trip - pickup) * 10) / 10 : null,
      tripToClearMs:
        trip != null && interrupt != null
          ? Math.round((interrupt - trip) * 10) / 10
          : trip != null && breaker != null
            ? Math.round((breaker - trip) * 10) / 10
            : null,
    };
  }, [timeline]);

  const supporting = (primary?.supporting_evidence_ids ?? [])
    .slice(0, 6)
    .map(humanizeEvidenceToken);

  if (eventLoading || !loaded) {
    return <div className="empty-state">Building event summary…</div>;
  }

  if (!event) {
    return (
      <EmptyState
        title="Event not found"
        description="Cannot build a summary without an event record."
        actions={[{ label: 'Back to events', to: '/events' }]}
      />
    );
  }

  const printedAt = format(new Date(), 'dd MMM yyyy HH:mm');
  const distanceOk = isDistanceApplicable({ fault, protection });
  const tripSummary = trips.length
    ? trips.map((t) => `${t.element} trip`).join('; ')
    : 'None asserted';

  return (
    <div>
      <div className={`${styles.toolbar} no-print`}>
        <div>
          <h1 style={{ fontSize: '1.1rem', margin: 0 }}>One-page event summary</h1>
          <p className="subtitle" style={{ margin: '4px 0 0' }}>
            Printable disturbance snapshot for protection review
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {id && <SharePackButton eventId={id} eventCode={event.event_id} />}
          <Link className="btn btn-sm" to={`/events/${id}/dr`}>
            DR workspace
          </Link>
          <Link className="btn btn-sm" to={`/events/${id}/overview`}>
            Overview
          </Link>
          <Link className="btn btn-sm" to={`/events/${id}/report`}>
            Full report
          </Link>
          <button type="button" className="btn btn-sm btn-primary" onClick={() => window.print()}>
            Print / PDF
          </button>
        </div>
      </div>

      <div className="no-print">
        <VerdictStrip
          faultType={fault?.fault_type ?? event.fault_type}
          tripSummary={tripSummary}
          consistency={overallCons}
          inconsistentCount={inconsistent.length}
          rcaTitle={primary?.title}
          eventStatus={event.status}
          decisionState={event.decision_state}
          nextLabel="Open DR @ fault"
          nextTo={`/events/${id}/dr`}
        />
      </div>

      <article className={styles.sheet} data-theme="light">
        <header className={styles.cover}>
          <div className={styles.header}>
            <div>
              <div className={styles.eyebrow}>Protection RCA · Disturbance summary</div>
              <h1 className={styles.title}>
                <span className="mono">{event.event_id}</span>
                {event.feeder ? ` · ${event.feeder}` : ''}
              </h1>
              <div className={styles.meta}>
                {substation} · {bay} · <span className="mono">{relay}</span>
                <br />
                {fmtWhen(event.event_datetime)}
                {event.nominal_voltage_kv != null && (
                  <>
                    {' '}
                    · {event.nominal_voltage_kv} kV / {event.nominal_frequency_hz ?? 50} Hz
                  </>
                )}
              </div>
            </div>
            <div className={styles.badges}>
              {event.status && <StatusBadge status={event.status} />}
              {event.decision_state && <StatusBadge status={event.decision_state} />}
              {event.data_quality && <DataQualityBadge quality={event.data_quality} />}
              {(fault?.fault_type || event.fault_type) && (
                <span className={`mono ${styles.fault}`}>
                  {fault?.fault_type ?? event.fault_type}
                </span>
              )}
            </div>
          </div>

          <div className={styles.kpis}>
            <div className={styles.kpi}>
              <span className={styles.kpiLbl}>Fault</span>
              <span className={styles.kpiVal}>{fault?.fault_type ?? event.fault_type ?? '—'}</span>
            </div>
            <div className={styles.kpi}>
              <span className={styles.kpiLbl}>Primary RCA</span>
              <span className={styles.kpiVal}>{primary?.title ?? 'Pending'}</span>
            </div>
            <div className={styles.kpi}>
              <span className={styles.kpiLbl}>Operated</span>
              <span className={styles.kpiVal}>{tripSummary}</span>
            </div>
            <div className={styles.kpi}>
              <span className={styles.kpiLbl}>Consistency</span>
              <span className={styles.kpiVal}>{overallCons.replace(/_/g, ' ')}</span>
            </div>
          </div>
        </header>

        <div className={styles.body}>
          <section className={styles.grid2}>
            <div className={styles.panel}>
              <h2>What happened</h2>
              <table className={styles.table}>
                <tbody>
                  <tr>
                    <th>Fault</th>
                    <td>
                      {fault?.fault_type ?? event.fault_type ?? 'Unknown'}
                      {fault?.status ? ` · ${fault.status.replace(/_/g, ' ')}` : ''}
                    </td>
                  </tr>
                  <tr>
                    <th>Phases</th>
                    <td>{fault?.involved_phases?.join(', ') ?? '—'}</td>
                  </tr>
                  <tr>
                    <th>Ground</th>
                    <td>
                      {fault?.ground_involved == null
                        ? '—'
                        : fault.ground_involved
                          ? 'Yes'
                          : 'No'}
                    </td>
                  </tr>
                  {distanceOk ? (
                    <tr>
                      <th>Location</th>
                      <td>{fmtDistance(fault?.distance_km)}</td>
                    </tr>
                  ) : (
                    <tr>
                      <th>Location</th>
                      <td>Not applicable for this scheme</td>
                    </tr>
                  )}
                  <tr>
                    <th>Trips</th>
                    <td>{tripSummary}</td>
                  </tr>
                  <tr>
                    <th>Pickups</th>
                    <td>
                      {pickups.length
                        ? pickups.map((p) => p.element).join(', ')
                        : 'None mapped / not asserted'}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className={styles.panel}>
              <h2>Settings &amp; consistency</h2>
              <table className={styles.table}>
                <tbody>
                  <tr>
                    <th>Setting source</th>
                    <td>{settingLabel(settingSource?.source)}</td>
                  </tr>
                  <tr>
                    <th>Version / group</th>
                    <td>
                      {settingLabel(settingSource?.version)} / {settingSource?.group || '—'}
                    </td>
                  </tr>
                  <tr>
                    <th>Active group</th>
                    <td>
                      {settingLabel(
                        settingSource?.active_group_status ?? settingSource?.verification_state,
                      )}
                    </td>
                  </tr>
                  <tr>
                    <th>Consistency</th>
                    <td>
                      {overallCons.replace(/_/g, ' ')} · {inconsistent.length} inconsistent /{' '}
                      {findings.length} findings
                    </td>
                  </tr>
                  <tr>
                    <th>Data quality</th>
                    <td>{event.data_quality?.replace(/_/g, ' ') ?? '—'}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section>
            <h2>Primary RCA</h2>
            {primary ? (
              <div className={styles.rcaBlock}>
                <div className={styles.rcaHead}>
                  <StatusBadge status={primary.status} />
                  <span className={styles.rcaTitle}>{primary.title}</span>
                  <span className={styles.rcaScore}>
                    {primary.confidence_level?.replace(/_/g, ' ') || '—'} ·{' '}
                    {formatConfidencePct(primary.confidence)}
                  </span>
                </div>
                {primary.statement && <p className={styles.statement}>{primary.statement}</p>}
                {supporting.length > 0 && (
                  <p className={styles.support}>
                    <strong>Supporting:</strong> {supporting.join('; ')}
                  </p>
                )}
              </div>
            ) : (
              <p className={styles.muted}>No RCA hypothesis yet — run analysis first.</p>
            )}
          </section>

          <section className={styles.grid2}>
            <div className={styles.panel}>
              <h2>
                Sequence of operation ({Math.min(timeline.length, 8)} of {timeline.length})
              </h2>
              {(timing.pickupToTripMs != null || timing.tripToClearMs != null) && (
                <div className={styles.timingBar}>
                  {timing.pickupToTripMs != null && (
                    <span>
                      Pickup → trip: <strong>{timing.pickupToTripMs} ms</strong>
                    </span>
                  )}
                  {timing.tripToClearMs != null && (
                    <span>
                      Trip → breaker/clear: <strong>{timing.tripToClearMs} ms</strong>
                    </span>
                  )}
                </div>
              )}
              {timeline.length === 0 ? (
                <p className={styles.muted}>No timeline entries.</p>
              ) : (
                <ol className={styles.timeline}>
                  {timeline.slice(0, 8).map((t) => (
                    <li key={t.id}>
                      <span className={styles.tTime}>
                        {t.t_us != null ? `${(t.t_us / 1000).toFixed(1)} ms` : '—'}
                      </span>
                      <span className={styles.tLabel}>{timelineLabel(t)}</span>
                    </li>
                  ))}
                </ol>
              )}
            </div>
            <div className={styles.panel}>
              <h2>Consistency findings</h2>
              {inconsistent.length === 0 ? (
                <p className={styles.muted}>
                  {findings.length
                    ? `No inconsistent findings (${findings.length} check${findings.length === 1 ? '' : 's'} reviewed).`
                    : 'No consistency findings yet.'}
                </p>
              ) : (
                <ul className={styles.findings}>
                  {inconsistent.slice(0, 6).map((f) => (
                    <li key={f.id}>
                      <span className="mono">{f.element || '—'}</span>
                      {f.explanation || formatCheckName(f.check_type) || f.status}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className={styles.panel}>
            <h2>Verify before closing</h2>
            <ul className={styles.verify}>
              {(primary?.recommended_actions?.length
                ? primary.recommended_actions
                : [
                    'Verify active relay setting group',
                    'Confirm channel mapping and COMTRADE validation',
                    'Review consistency findings — inconsistent ≠ automatic malfunction',
                    'Complete engineer disposition on Review',
                  ]
              )
                .slice(0, 5)
                .map((a) => (
                  <li key={a}>{a}</li>
                ))}
            </ul>
          </section>
        </div>

        <footer className={styles.footer}>
          Generated {printedAt} · Read-only analysis · No invented measurements
          {!looksLikeFileBatch(event.description) && event.description
            ? ` · ${event.description}`
            : ''}
        </footer>
      </article>
    </div>
  );
}
