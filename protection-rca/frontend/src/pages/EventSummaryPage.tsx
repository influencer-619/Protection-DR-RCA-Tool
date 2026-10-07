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
import { resolveDistanceApplicable, resolveFaultType } from '@/utils/schemeContext';
import { isEvidenceBackedAssert } from '@/utils/protectionOperateEvidence';
import {
  eventClassFromFault,
  formatConfidencePct,
  groundInvolvedLabel,
  humanizeEventClass,
  humanizeEvidenceToken,
  humanizeFaultType,
  isShuntFaultEventClass,
} from '@/utils/evidenceLabels';
import { formatCheckName } from '@/utils/findingValue';
import { buildTimelineCardInfo } from '@/utils/timelineCardInfo';
import { formatDrDate, parseApiDate } from '@/utils/dateTime';
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

/** One-page summary: only operate-critical steps (not every VA/VB/IA analog edge). */
const KEY_SEQUENCE_TYPES = new Set([
  'FAULT_INCEPTION',
  'PROTECTION_PICKUP',
  'PROTECTION_TRIP',
  'BREAKER_TRIP_COMMAND',
  '52A_CHANGE',
  '52B_CHANGE',
  'CURRENT_INTERRUPTION',
  'RECLOSE',
  'LOCKOUT',
  'INTERTRIP',
]);

function timelineType(t: TimelineEntry): string {
  return String(t.event_type || t.label || '')
    .trim()
    .toUpperCase()
    .replace(/\s+/g, '_');
}

function engineerKeySequence(entries: TimelineEntry[]): TimelineEntry[] {
  const key = entries.filter((t) => KEY_SEQUENCE_TYPES.has(timelineType(t)));
  // One row per type (first occurrence) — engineer cares about order, not 4× phase copies
  const seen = new Set<string>();
  const out: TimelineEntry[] = [];
  for (const t of key) {
    const ty = timelineType(t);
    if (seen.has(ty)) continue;
    seen.add(ty);
    out.push(t);
  }
  return out;
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
  // Scheme status (79/86/25) is not a fault-protection pickup — show separately
  const SCHEME_ELEMENTS = new Set(['79', '86', '25']);
  // Trips / pickups only when COMTRADE digital / clear SER evidence backs the assert
  const trips = protection.filter(
    (p) =>
      isEvidenceBackedAssert(p) &&
      (p.operation_type || '').toUpperCase().includes('TRIP'),
  );
  // Pickup row = elements that started (including those that later tripped).
  // Persist stores pickup+trip as operation_type TRIP with details.pickup=true.
  const pickups = protection.filter((p) => {
    if (!isEvidenceBackedAssert(p)) return false;
    if (SCHEME_ELEMENTS.has(String(p.element || '').toUpperCase())) return false;
    const ot = (p.operation_type || '').toUpperCase();
    if (ot.includes('RECLOSE') || ot.includes('LOCKOUT')) return false;
    const d = p.details as { pickup?: boolean } | null | undefined;
    return ot.includes('PICKUP') || d?.pickup === true;
  });
  const recloseOps = protection.filter((p) => {
    if (!isEvidenceBackedAssert(p)) return false;
    const el = String(p.element || '').toUpperCase();
    if (el === '79') return true;
    const ot = (p.operation_type || '').toUpperCase();
    return ot.includes('RECLOSE');
  });
  const inconsistent = findings.filter((f) => f.status === 'INCONSISTENT');
  const plantExtra = (event?.extra as Record<string, string> | undefined) ?? {};
  const plantLabels =
    (event?.extra as { plant_labels?: Record<string, string> } | undefined)?.plant_labels ?? {};

  const substation =
    event?.substation_name ?? plantLabels.substation_name ?? plantExtra.substation_name ?? '—';
  const bay = event?.bay_name ?? plantLabels.bay_name ?? plantExtra.bay_name ?? '—';
  const relay = event?.relay_tag ?? plantLabels.relay_tag ?? plantExtra.relay_tag ?? '—';

  const timing = useMemo(() => {
    type Row = { ms: number; src: string };
    const rank = (src: string) => {
      const s = src.toUpperCase();
      if (s.startsWith('DIGITAL:') || s.startsWith('ANALOG:')) return 0;
      if (s.startsWith('SOE')) return 2;
      if (s.includes('REPORT')) return 3;
      return 1;
    };
    const rowsOf = (type: string): Row[] =>
      timeline
        .filter((t) => (t.event_type || '').toLowerCase() === type && t.t_us != null)
        .map((t) => ({ ms: t.t_us! / 1000, src: t.source || '' }));

    const pickupsT = rowsOf('protection_pickup').sort(
      (a, b) => rank(a.src) - rank(b.src) || a.ms - b.ms,
    );
    const tripsT = rowsOf('protection_trip').sort(
      (a, b) => rank(a.src) - rank(b.src) || a.ms - b.ms,
    );
    // Prefer COMTRADE digital pair with trip >= pickup (avoid early SOE skew)
    let pickup: number | null = null;
    let trip: number | null = null;
    for (const p of pickupsT) {
      const later = tripsT.find((tr) => tr.ms + 1e-9 >= p.ms);
      if (later) {
        pickup = p.ms;
        trip = later.ms;
        break;
      }
    }
    if (pickup == null && pickupsT[0]) pickup = pickupsT[0].ms;
    if (trip == null && tripsT[0]) trip = tripsT[0].ms;

    const interrupt = rowsOf('current_interruption').sort((a, b) => a.ms - b.ms)[0]?.ms;
    const breaker = rowsOf('52a_change').sort((a, b) => a.ms - b.ms)[0]?.ms;
    return {
      pickupToTripMs:
        pickup != null && trip != null && trip >= pickup
          ? Math.round((trip - pickup) * 10) / 10
          : null,
      tripToClearMs:
        trip != null && interrupt != null
          ? Math.round((interrupt - trip) * 10) / 10
          : trip != null && breaker != null
            ? Math.round((breaker - trip) * 10) / 10
            : null,
    };
  }, [timeline]);

  const keySequence = useMemo(() => engineerKeySequence(timeline), [timeline]);

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
  const rawFaultType = resolveFaultType({
    fault,
    eventFaultType: event?.fault_type,
    eventExtra: (event?.extra || {}) as Record<string, unknown>,
  });
  const eventClass = eventClassFromFault(fault);
  const displayFaultType = humanizeFaultType(rawFaultType, eventClass);
  const distanceOk = resolveDistanceApplicable({
    fault,
    protection,
    eventExtra: (event?.extra || {}) as Record<string, unknown>,
  });
  const tripSummary = trips.length
    ? trips.map((t) => `${t.element} trip`).join('; ')
    : pickups.length
      ? `${[...new Set(pickups.map((p) => p.element))].join(', ')} — start only (no trip assert)`
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
          faultType={displayFaultType}
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
                DR {formatDrDate(event.event_datetime)}
                {' · '}
                Created{' '}
                {(() => {
                  const d = parseApiDate(event.created_at);
                  return d ? format(d, 'dd MMM yyyy HH:mm:ss') : '—';
                })()}
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
              {rawFaultType && (
                <span className={`mono ${styles.fault}`}>{displayFaultType}</span>
              )}
            </div>
          </div>

          <div className={styles.kpis}>
            <div className={styles.kpi}>
              <span className={styles.kpiLbl}>Event class</span>
              <span className={styles.kpiVal}>
                {humanizeEventClass(eventClassFromFault(fault))}
              </span>
            </div>
            <div className={styles.kpi}>
              <span className={styles.kpiLbl}>Fault</span>
              <span className={styles.kpiVal}>{displayFaultType}</span>
            </div>
            <div className={styles.kpi}>
              <span className={styles.kpiLbl}>Primary RCA</span>
              <span className={styles.kpiVal}>{primary?.title ?? 'Pending'}</span>
            </div>
            <div className={styles.kpi}>
              <span className={styles.kpiLbl}>Operated</span>
              <span className={styles.kpiVal}>{tripSummary}</span>
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
                    <th>Event class</th>
                    <td>{humanizeEventClass(eventClassFromFault(fault))}</td>
                  </tr>
                  <tr>
                    <th>Fault</th>
                    <td>
                      {displayFaultType}
                      {fault?.status && isShuntFaultEventClass(eventClass)
                        ? ` · ${fault.status.replace(/_/g, ' ')}`
                        : ''}
                    </td>
                  </tr>
                  <tr>
                    <th>Phases</th>
                    <td>
                      {isShuntFaultEventClass(eventClassFromFault(fault))
                        ? fault?.involved_phases?.join(', ') ?? '—'
                        : '—'}
                    </td>
                  </tr>
                  <tr>
                    <th>Ground</th>
                    <td>
                      {groundInvolvedLabel(
                        eventClassFromFault(fault),
                        fault?.ground_involved,
                      )}
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
                      {[...new Set(pickups.map((p) => p.element))]
                        .filter(Boolean)
                        .join(', ') || 'None asserted'}
                    </td>
                  </tr>
                  <tr>
                    <th>Reclose</th>
                    <td>
                      {recloseOps.length
                        ? [...new Set(recloseOps.map((p) => p.element))]
                            .filter(Boolean)
                            .map((el) => (el === '79' ? '79 (AR issued)' : el))
                            .join(', ')
                        : 'None asserted'}
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
              <h2>Key operate sequence</h2>
              <p className={styles.muted} style={{ marginTop: 0, marginBottom: 8, fontSize: '0.8rem' }}>
                Engineer view: fault → pickup → trip → clear
                {timeline.length > keySequence.length
                  ? ` (${keySequence.length} of ${timeline.length} timeline events)`
                  : ''}
                {id ? (
                  <>
                    {' · '}
                    <Link to={`/events/${id}/timeline`}>Full timeline</Link>
                  </>
                ) : null}
              </p>
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
              {keySequence.length === 0 ? (
                <p className={styles.muted}>
                  No pickup / trip / breaker steps mapped yet
                  {timeline.length ? ` (${timeline.length} other timeline edges recorded).` : '.'}
                </p>
              ) : (
                <ol className={styles.timeline}>
                  {keySequence.map((t) => {
                    const info = buildTimelineCardInfo(t);
                    const val =
                      info.facts.find((f) => f.label === 'RMS')?.value ||
                      info.facts.find((f) => f.label === 'Transition')?.value ||
                      info.facts.find((f) => f.label === 'State')?.value ||
                      null;
                    return (
                      <li key={t.id}>
                        <span className={styles.tTime}>
                          {t.t_us != null ? `${(t.t_us / 1000).toFixed(1)} ms` : '—'}
                        </span>
                        <span className={styles.tLabel}>{timelineLabel(t)}</span>
                        {val && <span className={`mono ${styles.muted}`}> · {val}</span>}
                      </li>
                    );
                  })}
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
