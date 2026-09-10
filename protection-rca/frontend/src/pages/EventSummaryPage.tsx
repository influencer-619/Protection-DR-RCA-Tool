import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
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
import styles from './EventSummaryPage.module.css';

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
    event?.substation_name ?? plantLabels.substation_name ?? plantExtra.substation_name ?? 'UNKNOWN';
  const bay = event?.bay_name ?? plantLabels.bay_name ?? plantExtra.bay_name ?? 'NOT VERIFIED';
  const relay =
    event?.relay_tag ?? plantLabels.relay_tag ?? plantExtra.relay_tag ?? 'NOT VERIFIED';

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

  const printedAt = new Date().toISOString();

  return (
    <div>
      <div className={`${styles.toolbar} no-print`}>
        <div>
          <h1 style={{ fontSize: '1.1rem', margin: 0 }}>One-page event summary</h1>
          <p className="subtitle" style={{ margin: '4px 0 0' }}>
            Printable disturbance snapshot — only verified analysis outputs, no invented values
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

      <VerdictStrip
        faultType={fault?.fault_type ?? event.fault_type}
        tripSummary={
          trips.length
            ? trips.map((t) => `${t.element} ${t.operation_type}`).join('; ')
            : 'None asserted'
        }
        consistency={overallCons}
        inconsistentCount={inconsistent.length}
        rcaTitle={primary?.title}
        rcaCode={primary?.hypothesis_code}
        eventStatus={event.status}
        decisionState={event.decision_state}
        nextLabel="Open DR @ fault"
        nextTo={`/events/${id}/dr`}
      />

      <article className={styles.sheet}>
        <header className={styles.header}>
          <div>
            <div className={styles.eyebrow}>Protection RCA · Disturbance summary</div>
            <h1 className={styles.title}>
              <span className="mono">{event.event_id}</span>
              {event.feeder ? ` / ${event.feeder}` : ''}
            </h1>
            <div className={styles.meta}>
              {substation} · {bay} · <span className="mono">{relay}</span>
              {event.event_datetime && (
                <> · {new Date(event.event_datetime).toISOString()}</>
              )}
            </div>
          </div>
          <div className={styles.badges}>
            {event.status && <StatusBadge status={event.status} />}
            {event.decision_state && <StatusBadge status={event.decision_state} />}
            {event.data_quality && <DataQualityBadge quality={event.data_quality} />}
            {event.fault_type && <span className={`mono ${styles.fault}`}>{event.fault_type}</span>}
          </div>
        </header>

        <section className={styles.grid2}>
          <div>
            <h2>What happened</h2>
            <table className={styles.table}>
              <tbody>
                <tr>
                  <th>Fault</th>
                  <td>
                    {fault?.fault_type ?? event.fault_type ?? 'UNKNOWN'}
                    {fault?.status ? ` (${fault.status})` : ''}
                  </td>
                </tr>
                <tr>
                  <th>Phases</th>
                  <td className="mono">{fault?.involved_phases?.join(', ') ?? '—'}</td>
                </tr>
                <tr>
                  <th>Ground</th>
                  <td>
                    {fault?.ground_involved == null
                      ? 'NOT AVAILABLE'
                      : fault.ground_involved
                        ? 'Yes'
                        : 'No'}
                  </td>
                </tr>
                {isDistanceApplicable({ fault, protection }) ? (
                  <tr>
                    <th>Location (km)</th>
                    <td>
                      {fault?.distance_km != null
                        ? `${fault.distance_km} km`
                        : 'NOT CALCULABLE'}
                    </td>
                  </tr>
                ) : (
                  <tr>
                    <th>Location / Z</th>
                    <td>Not applicable (no distance / line-location evidence for this case)</td>
                  </tr>
                )}
                <tr>
                  <th>Trips asserted</th>
                  <td>
                    {trips.length
                      ? trips.map((t) => `${t.element} ${t.operation_type}`).join('; ')
                      : 'None mapped / not asserted'}
                  </td>
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

          <div>
            <h2>Settings & consistency</h2>
            <table className={styles.table}>
              <tbody>
                <tr>
                  <th>Setting source</th>
                  <td className="mono">{settingSource?.source ?? 'NOT VERIFIED'}</td>
                </tr>
                <tr>
                  <th>Version / group</th>
                  <td className="mono">
                    {settingSource?.version ?? 'NOT VERIFIED'} /{' '}
                    {settingSource?.group ?? 'NOT VERIFIED'}
                  </td>
                </tr>
                <tr>
                  <th>Active group</th>
                  <td>
                    {settingSource?.active_group_status ??
                      settingSource?.verification_state ??
                      'NOT VERIFIED'}
                  </td>
                </tr>
                <tr>
                  <th>Consistency</th>
                  <td>
                    {overallCons} · {inconsistent.length} inconsistent / {findings.length} findings
                  </td>
                </tr>
                <tr>
                  <th>Nominal</th>
                  <td>
                    {event.nominal_voltage_kv ?? 'UNKNOWN'} kV /{' '}
                    {event.nominal_frequency_hz ?? 50} Hz
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section>
          <h2>Primary RCA</h2>
          {primary ? (
            <>
              <div className={styles.rcaHead}>
                <StatusBadge status={primary.status} />
                <span className="mono">{primary.hypothesis_code}</span>
                <strong>{primary.title}</strong>
                <span className="mono">
                  {primary.confidence_level} ({((primary.confidence ?? 0) * 100).toFixed(0)}%)
                </span>
              </div>
              <p className={styles.statement}>{primary.statement}</p>
              {primary.explanation && <p className={styles.explain}>{primary.explanation}</p>}
            </>
          ) : (
            <p className={styles.muted}>No RCA hypothesis yet — run analysis first.</p>
          )}
        </section>

        <section className={styles.grid2}>
          <div>
            <h2>Key timeline ({Math.min(timeline.length, 8)} of {timeline.length})</h2>
            {timeline.length === 0 ? (
              <p className={styles.muted}>No timeline entries.</p>
            ) : (
              <ol className={styles.timeline}>
                {timeline.slice(0, 8).map((t) => (
                  <li key={t.id}>
                    <span className="mono">
                      {t.t_us != null ? `${(t.t_us / 1000).toFixed(2)} ms` : '—'}
                    </span>
                    <span>{t.label || t.event_type}</span>
                  </li>
                ))}
              </ol>
            )}
          </div>
          <div>
            <h2>Inconsistent findings ({inconsistent.length})</h2>
            {inconsistent.length === 0 ? (
              <p className={styles.muted}>
                {findings.length
                  ? 'No INCONSISTENT findings (others may be UNVERIFIABLE).'
                  : 'No consistency findings yet.'}
              </p>
            ) : (
              <ul className={styles.findings}>
                {inconsistent.slice(0, 6).map((f) => (
                  <li key={f.id}>
                    <span className="mono">{f.element || f.check_type}</span>
                    {f.explanation || f.check_type || f.status}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section>
          <h2>Verify before closing</h2>
          <ul className={styles.verify}>
            {(primary?.recommended_actions?.length
              ? primary.recommended_actions
              : [
                  'Verify active relay setting group',
                  'Confirm channel mapping and COMTRADE validation',
                  'Review consistency findings — INCONSISTENT ≠ automatic malfunction',
                  'Complete engineer disposition on Review',
                ]
            )
              .slice(0, 5)
              .map((a) => (
                <li key={a}>{a}</li>
              ))}
          </ul>
        </section>

        <footer className={styles.footer}>
          Generated {printedAt} · Read-only analysis · No generative AI · No invented measurements
          {event.description ? ` · ${event.description}` : ''}
        </footer>
      </article>
    </div>
  );
}
