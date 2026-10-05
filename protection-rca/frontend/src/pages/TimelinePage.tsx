import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { format, isValid, parseISO } from 'date-fns';
import { api } from '@/services/api';
import type { TimelineEntry } from '@/types';
import { EmptyState } from '@/components/EmptyState';
import { SettingsObservedStrip } from '@/components/SettingsObservedStrip';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import {
  buildTimelineCardInfo,
  matchTimelineType,
  timelineEventTitle,
} from '@/utils/timelineCardInfo';
import styles from './TimelinePage.module.css';

function digitalId(e: TimelineEntry): string {
  const info = buildTimelineCardInfo(e);
  return info.title || e.label || e.event_type || '—';
}

/** Wall-clock from CFG start + relative (DR) or SOE stamp. */
function fmtAbsolute(raw?: string | null): string {
  if (!raw) return '—';
  try {
    const d = parseISO(raw);
    if (!isValid(d)) return raw;
    return format(d, 'yyyy-MM-dd HH:mm:ss.SSS');
  } catch {
    return raw;
  }
}

function assertedValue(e: TimelineEntry): string {
  const info = buildTimelineCardInfo(e);
  if (info.transition) return info.transition;
  const state = info.facts.find((f) => f.label === 'State');
  if (state) return state.value;
  const d = e.details as Record<string, unknown> | null | undefined;
  if (d && typeof d.value !== 'undefined') return String(d.value);
  if (d && typeof d.asserted !== 'undefined') return String(d.asserted);
  const t = (e.event_type || '').toUpperCase();
  if (t.includes('DROPOUT') || t.includes('RESET') || t.includes('DPO')) return 'False';
  return 'True';
}

function firstObservedSeconds(entries: TimelineEntry[], types: string[]): number | null {
  const hit = [...entries]
    .filter((t) => matchTimelineType(t.event_type || '', types))
    .sort((a, b) => (a.t_us ?? Number.MAX_SAFE_INTEGER) - (b.t_us ?? Number.MAX_SAFE_INTEGER))[0];
  return hit?.t_us != null ? Number(hit.t_us) / 1e6 : null;
}

export function TimelinePage() {
  const { id } = useParams<{ id: string }>();
  const { event, analysisRevision } = useEventOrWorkspace(id);
  const [entries, setEntries] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<'table' | 'cards'>('table');

  const device =
    event?.relay_tag ||
    (event?.extra as { relay_tag?: string; plant_labels?: { relay_tag?: string } } | undefined)
      ?.relay_tag ||
    (event?.extra as { plant_labels?: { relay_tag?: string } } | undefined)?.plant_labels
      ?.relay_tag ||
    '—';

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    void api
      .getTimeline(id)
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, [id, analysisRevision]);

  const sorted = useMemo(
    () =>
      [...entries].sort((a, b) => {
        const ta = a.t_us ?? Number.MAX_SAFE_INTEGER;
        const tb = b.t_us ?? Number.MAX_SAFE_INTEGER;
        return ta - tb;
      }),
    [entries],
  );

  const observed = useMemo(
    () => ({
      pickup_s: firstObservedSeconds(entries, ['protection_pickup']),
      trip_s: firstObservedSeconds(entries, ['protection_trip', 'breaker_trip_command']),
      breaker_s: firstObservedSeconds(entries, ['52a_change', '52b_change']),
      interrupt_s: firstObservedSeconds(entries, ['current_interruption']),
    }),
    [entries],
  );

  const expected = useMemo(() => {
    const extra = (event?.extra || {}) as Record<string, unknown>;
    const rs = (extra.relay_settings || {}) as Record<string, Record<string, unknown>>;
    const bf = rs['50BF'] || {};
    return {
      pickup_s: null as number | null,
      trip_s: null as number | null,
      bf_timer_s: typeof bf.bf_timer_s === 'number' ? Number(bf.bf_timer_s) : null,
      source: (extra.setting_source as string) || null,
    };
  }, [event]);

  if (loading) return <div className="empty-state">Loading sequence of operation…</div>;

  if (!entries.length) {
    return (
      <EmptyState
        title="No sequence of operation yet"
        description="Built during analysis from COMTRADE digitals, SOE CSV, and relay event reports."
        tips={[
          'Upload CFG/DAT (or ZIP) on Files',
          'Optionally add soe.csv / relay_event_report.txt',
          'Run analysis from the event header',
        ]}
        actions={[
          { label: 'Go to Files', to: id ? `/events/${id}/files` : '/events' },
          { label: 'Open Waveforms', to: id ? `/events/${id}/waveforms` : '/events' },
        ]}
      />
    );
  }

  return (
    <div>
      <div className="page-header" style={{ padding: 0, marginBottom: 16 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Field sequence of operation</h1>
          <p className="subtitle">
            Chronological protection / digital changes · {entries.length} entries (AFAS-style)
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            type="button"
            className={`btn btn-sm ${view === 'table' ? 'btn-primary' : ''}`}
            onClick={() => setView('table')}
          >
            Table
          </button>
          <button
            type="button"
            className={`btn btn-sm ${view === 'cards' ? 'btn-primary' : ''}`}
            onClick={() => setView('cards')}
          >
            Cards
          </button>
        </div>
      </div>

      <SettingsObservedStrip expected={expected} observed={observed} />

      {view === 'table' ? (
        <div className="panel">
          <div className="panel-body" style={{ padding: 0, overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time (rel)</th>
                  <th title="CFG start + relative sample time (DR), or SOE wall-clock">
                    Absolute time
                  </th>
                  <th>Relay / device</th>
                  <th>Digital / event</th>
                  <th>Type</th>
                  <th>Value</th>
                  <th>Source</th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((e) => (
                  <tr key={e.id}>
                    <td className="mono">
                      {e.t_us != null ? `${(e.t_us / 1000).toFixed(3)} ms` : '—'}
                    </td>
                    <td
                      className="mono"
                      style={{ fontSize: '0.75rem' }}
                      title={e.absolute_time ?? undefined}
                    >
                      {fmtAbsolute(e.absolute_time)}
                    </td>
                    <td className="mono">{device}</td>
                    <td>{digitalId(e)}</td>
                    <td className="mono" style={{ fontSize: '0.75rem' }}>
                      {timelineEventTitle(e.event_type)}
                    </td>
                    <td className="mono">{assertedValue(e)}</td>
                    <td style={{ fontSize: '0.75rem' }}>{e.source ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <ol className={styles.timeline}>
          {sorted.map((e) => {
            const info = buildTimelineCardInfo(e);
            return (
              <li key={e.id} className={styles.item}>
                <div className={styles.marker} />
                <div className={styles.card}>
                  <div className={styles.top}>
                    <span className={`mono ${styles.t}`}>
                      {e.t_us != null ? `t = ${(e.t_us / 1000).toFixed(2)} ms` : '—'}
                    </span>
                    <span className={styles.type}>{timelineEventTitle(e.event_type)}</span>
                    {e.confidence != null && (
                      <span className={`mono ${styles.conf}`}>
                        {(e.confidence * 100).toFixed(0)}%
                      </span>
                    )}
                  </div>
                  <div className={styles.label}>{info.title}</div>
                  {info.summary && <p className={styles.desc}>{info.summary}</p>}
                  {info.facts.length > 0 && (
                    <dl className={styles.facts}>
                      {info.facts.map((f) => (
                        <div key={`${e.id}-${f.label}`} className={styles.fact}>
                          <dt>{f.label}</dt>
                          <dd className="mono">{f.value}</dd>
                        </div>
                      ))}
                    </dl>
                  )}
                  <div className={styles.meta}>
                    {e.absolute_time && (
                      <span className="mono" title="Absolute time (CFG start + relative, or SOE)">
                        {fmtAbsolute(e.absolute_time)}
                      </span>
                    )}
                    {e.source && <span>Source: {e.source}</span>}
                    {device !== '—' && <span>Device: {device}</span>}
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
