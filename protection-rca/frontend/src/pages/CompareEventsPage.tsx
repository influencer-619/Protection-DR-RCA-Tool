import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { Event, FaultClassification, ProtectionOperation, RcaHypothesis } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { VerdictStrip } from '@/components/VerdictStrip';
import { EmptyState } from '@/components/EmptyState';
import { Skeleton } from '@/components/Skeleton';
import { isDistanceApplicable } from '@/utils/schemeContext';
import styles from './CompareEventsPage.module.css';

type Side = {
  event: Event | null;
  fault: FaultClassification | null;
  rca: RcaHypothesis | null;
  cons: string;
  protection: ProtectionOperation[];
  error?: string;
};

async function loadSide(id: string): Promise<Side> {
  try {
    const [event, faultRaw, rcaList, cons, protection] = await Promise.all([
      api.getEvent(id),
      api.getFaultClassification(id).catch(() => null),
      api.getRca(id).catch(() => [] as RcaHypothesis[]),
      api.getConsistency(id).then((r) => r.overall_status).catch(() => 'NOT_AVAILABLE'),
      api.getProtection(id).catch(() => [] as ProtectionOperation[]),
    ]);
    const fault = Array.isArray(faultRaw) ? faultRaw[0] ?? null : faultRaw;
    const list = Array.isArray(rcaList) ? rcaList : [];
    const primary = list.find((h) => h.rank === 1) ?? list[0] ?? null;
    return { event, fault, rca: primary, cons, protection: Array.isArray(protection) ? protection : [] };
  } catch (e) {
    return {
      event: null,
      fault: null,
      rca: null,
      cons: 'NOT_AVAILABLE',
      protection: [],
      error: e instanceof Error ? e.message : 'Failed to load',
    };
  }
}

function SideCard({ side, label }: { side: Side; label: string }) {
  if (side.error || !side.event) {
    return (
      <div className={styles.card}>
        <h2>{label}</h2>
        <p className={styles.muted}>{side.error || 'Select an event'}</p>
      </div>
    );
  }
  const ev = side.event;
  const distOk = isDistanceApplicable({ fault: side.fault, protection: side.protection });
  return (
    <div className={styles.card}>
      <div className={styles.cardHead}>
        <h2>
          {label}: <span className="mono">{ev.event_id}</span>
        </h2>
        <div className={styles.links}>
          <Link className="btn btn-sm" to={`/events/${ev.id}/summary`}>
            Summary
          </Link>
          <Link className="btn btn-sm btn-primary" to={`/events/${ev.id}/dr`}>
            DR
          </Link>
        </div>
      </div>
      <VerdictStrip
        compact
        faultType={side.fault?.fault_type ?? ev.fault_type}
        consistency={side.cons}
        rcaTitle={side.rca?.title}
        rcaCode={side.rca?.hypothesis_code}
        eventStatus={ev.status}
        decisionState={ev.decision_state}
      />
      <table className={styles.table}>
        <tbody>
          <tr>
            <th>Station / bay</th>
            <td>
              {ev.substation_name ?? '—'} / {ev.bay_name ?? '—'}
            </td>
          </tr>
          <tr>
            <th>Feeder / relay</th>
            <td>
              {ev.feeder ?? '—'} / <span className="mono">{ev.relay_tag ?? '—'}</span>
            </td>
          </tr>
          <tr>
            <th>When</th>
            <td className="mono">
              {ev.event_datetime ? new Date(ev.event_datetime).toLocaleString() : '—'}
            </td>
          </tr>
          <tr>
            <th>Phases</th>
            <td className="mono">{side.fault?.involved_phases?.join(', ') ?? '—'}</td>
          </tr>
          <tr>
            <th>Distance</th>
            <td>
              {!distOk
                ? 'Not applicable'
                : side.fault?.distance_km != null
                  ? `${side.fault.distance_km} km`
                  : 'NOT CALCULABLE'}
            </td>
          </tr>
          <tr>
            <th>RCA</th>
            <td>{side.rca?.statement ?? '—'}</td>
          </tr>
        </tbody>
      </table>
      {ev.status && <StatusBadge status={ev.status} />}
    </div>
  );
}

export function CompareEventsPage() {
  const [params, setParams] = useSearchParams();
  const aId = params.get('a') || '';
  const bId = params.get('b') || '';
  const [events, setEvents] = useState<Event[]>([]);
  const [left, setLeft] = useState<Side | null>(null);
  const [right, setRight] = useState<Side | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    void api.getEvents().then(setEvents).catch(() => setEvents([]));
  }, []);

  useEffect(() => {
    if (!aId && !bId) {
      setLeft(null);
      setRight(null);
      return;
    }
    setLoading(true);
    void Promise.all([
      aId ? loadSide(aId) : Promise.resolve(null),
      bId ? loadSide(bId) : Promise.resolve(null),
    ])
      .then(([l, r]) => {
        setLeft(l);
        setRight(r);
      })
      .finally(() => setLoading(false));
  }, [aId, bId]);

  const options = useMemo(
    () =>
      events.map((e) => ({
        id: e.id,
        label: `${e.event_id}${e.feeder ? ` · ${e.feeder}` : ''}`,
      })),
    [events],
  );

  if (!events.length && !loading) {
    return (
      <EmptyState
        title="No events to compare"
        description="Create and analyse at least two disturbance events, then compare verdicts side by side."
        actions={[{ label: 'Events', to: '/events', primary: true }]}
      />
    );
  }

  return (
    <div className={`page ${styles.page}`}>
      <div className="page-header">
        <div>
          <h1>Compare events</h1>
          <p className="subtitle">Side-by-side fault · consistency · RCA (no invented values)</p>
        </div>
        <Link to="/events" className="btn">
          Back to events
        </Link>
      </div>

      <div className={styles.pickers}>
        <label>
          Event A
          <select
            className="input"
            value={aId}
            onChange={(e) => {
              const next = new URLSearchParams(params);
              if (e.target.value) next.set('a', e.target.value);
              else next.delete('a');
              setParams(next);
            }}
          >
            <option value="">—</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
        <label>
          Event B
          <select
            className="input"
            value={bId}
            onChange={(e) => {
              const next = new URLSearchParams(params);
              if (e.target.value) next.set('b', e.target.value);
              else next.delete('b');
              setParams(next);
            }}
          >
            <option value="">—</option>
            {options.map((o) => (
              <option key={o.id} value={o.id}>
                {o.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {loading && <Skeleton rows={6} label="Loading comparison" />}

      {!loading && (
        <div className={styles.grid}>
          <SideCard
            side={left || { event: null, fault: null, rca: null, cons: '', protection: [] }}
            label="A"
          />
          <SideCard
            side={right || { event: null, fault: null, rca: null, cons: '', protection: [] }}
            label="B"
          />
        </div>
      )}
    </div>
  );
}
