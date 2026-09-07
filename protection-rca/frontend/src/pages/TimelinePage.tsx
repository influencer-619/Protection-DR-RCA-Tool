import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { TimelineEntry } from '@/types';
import { EmptyState } from '@/components/EmptyState';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import styles from './TimelinePage.module.css';

function digitalId(e: TimelineEntry): string {
  return e.label || e.event_type || '—';
}

function assertedValue(e: TimelineEntry): string {
  const d = e.details as Record<string, unknown> | null | undefined;
  if (d && typeof d.value !== 'undefined') return String(d.value);
  if (d && typeof d.asserted !== 'undefined') return String(d.asserted);
  const t = (e.event_type || '').toUpperCase();
  if (t.includes('DROPOUT') || t.includes('RESET') || t.includes('DPO')) return 'False';
  return 'True';
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

      {view === 'table' ? (
        <div className="panel">
          <div className="panel-body" style={{ padding: 0, overflowX: 'auto' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Time (rel)</th>
                  <th>Absolute time</th>
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
                    <td className="mono" style={{ fontSize: '0.75rem' }}>
                      {e.absolute_time ?? '—'}
                    </td>
                    <td className="mono">{device}</td>
                    <td>{digitalId(e)}</td>
                    <td className="mono" style={{ fontSize: '0.75rem' }}>
                      {e.event_type.replace(/_/g, ' ')}
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
          {sorted.map((e) => (
            <li key={e.id} className={styles.item}>
              <div className={styles.marker} />
              <div className={styles.card}>
                <div className={styles.top}>
                  <span className={`mono ${styles.t}`}>
                    {e.t_us != null ? `t = ${(e.t_us / 1000).toFixed(2)} ms` : '—'}
                  </span>
                  <span className={styles.type}>{e.event_type.replace(/_/g, ' ')}</span>
                  {e.confidence != null && (
                    <span className={`mono ${styles.conf}`}>{(e.confidence * 100).toFixed(0)}%</span>
                  )}
                </div>
                <div className={styles.label}>{e.label}</div>
                {e.description && <p className={styles.desc}>{e.description}</p>}
                <div className={styles.meta}>
                  {e.absolute_time && <span className="mono">{e.absolute_time}</span>}
                  {e.source && <span>Source: {e.source}</span>}
                </div>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
