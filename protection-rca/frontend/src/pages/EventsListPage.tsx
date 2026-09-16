import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { format, isValid, parseISO } from 'date-fns';
import { api } from '@/services/api';
import type { Event } from '@/types';
import { EventStatusCell } from '@/components/EventStatusCell';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { SeverityBadge } from '@/components/SeverityBadge';
import { DataQualityBadge } from '@/components/DataQualityBadge';
import { getLastEvent, pruneRecentEvents, removeRecentEvent } from '@/utils/recentEvents';

const QUEUE_LABELS: Record<string, string> = {
  awaiting_analysis: 'Awaiting analysis',
  awaiting_review: 'Awaiting review',
  completed_reports: 'Completed reports',
  consistency_issues: 'Consistency issues',
  high_severity: 'High severity findings',
  rca_inconclusive: 'RCA inconclusive',
  parser_dq_issues: 'Parser / DQ issues',
};

function eventExtra(ev: Event): Record<string, unknown> {
  return (ev.extra as Record<string, unknown> | null | undefined) ?? {};
}

function eventSearchText(ev: Event): string {
  const extra = eventExtra(ev);
  const parts = [
    ev.event_id,
    ev.substation_name,
    extra.substation_name,
    ev.bay_name,
    extra.bay_name,
    ev.relay_tag,
    extra.relay_tag,
    ev.feeder,
    ev.description,
    ev.fault_type,
    ev.protection_summary,
    ev.status,
    ev.decision_state,
    ev.data_quality,
    ev.severity_summary,
  ];
  return parts
    .filter((p) => p != null && String(p).trim() !== '')
    .join(' ')
    .toLowerCase();
}

/** Parse datetime-local value as a local Date (no UTC shift). */
function parseLocalInput(value: string): Date | null {
  if (!value) return null;
  const m = value.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!m) {
    const d = new Date(value);
    return isValid(d) ? d : null;
  }
  const d = new Date(
    Number(m[1]),
    Number(m[2]) - 1,
    Number(m[3]),
    Number(m[4]),
    Number(m[5]),
    m[6] ? Number(m[6]) : 0,
    0,
  );
  return isValid(d) ? d : null;
}

function eventWhen(ev: Event): Date | null {
  const raw = ev.event_datetime || ev.created_at;
  if (!raw) return null;
  try {
    const d = parseISO(raw);
    return isValid(d) ? d : null;
  } catch {
    return null;
  }
}

export function EventsListPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [filter, setFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const queue = searchParams.get('queue') ?? undefined;

  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');

  useEffect(() => {
    setLoading(true);
    const params: {
      queue?: string;
      page_size?: number;
    } = { page_size: 200 };
    if (queue) params.queue = queue;
    void api
      .getEvents(params)
      .then(setEvents)
      .catch(() => setEvents([]))
      .finally(() => setLoading(false));
  }, [queue]);

  useEffect(() => {
    const st = location.state as { openCreate?: boolean } | null;
    if (st?.openCreate) {
      navigate('/plant', { replace: true });
    }
  }, [location.state, navigate]);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const from = parseLocalInput(dateFrom);
    let to = parseLocalInput(dateTo);
    // If "To" is at midnight, treat as end of that calendar day (inclusive).
    if (to && /T00:00(:00)?$/.test(dateTo)) {
      to = new Date(to);
      to.setHours(23, 59, 59, 999);
    }

    return events.filter((e) => {
      if (q && !eventSearchText(e).includes(q)) return false;
      if (from || to) {
        const when = eventWhen(e);
        if (!when) return false;
        if (from && when < from) return false;
        if (to && when > to) return false;
      }
      return true;
    });
  }, [events, filter, dateFrom, dateTo]);

  const hasActiveFilters = Boolean(filter.trim() || dateFrom || dateTo || queue);

  const clearFilters = () => {
    setFilter('');
    setDateFrom('');
    setDateTo('');
    if (queue) setSearchParams({});
  };

  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<Event | null>(null);
  const [last, setLast] = useState(() => getLastEvent());

  useEffect(() => {
    if (loading) return;
    const pruned = pruneRecentEvents(events.map((e) => e.id));
    setLast(pruned[0] ?? null);
  }, [events, loading]);

  const onDelete = async () => {
    const ev = pendingDelete;
    if (!ev) return;
    setDeletingId(ev.id);
    try {
      await api.deleteEvent(ev.id);
      removeRecentEvent(ev.id);
      setEvents((prev) => prev.filter((e) => e.id !== ev.id));
      setPendingDelete(null);
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Failed to delete event');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>All events</h1>
          <p className="subtitle">
            {queue && QUEUE_LABELS[queue]
              ? `Filtered: ${QUEUE_LABELS[queue]}`
              : 'Global list — create and upload under Plant → IED'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {last && (
            <Link
              to={`/events/${last.id}/summary`}
              className="btn btn-primary"
              title={last.event_id}
            >
              Continue{' '}
              {last.event_id.length > 12 ? `${last.event_id.slice(0, 12)}…` : last.event_id}
            </Link>
          )}
          <Link to="/plant" className="btn btn-primary">
            Open Plant
          </Link>
          <Link to="/events/compare" className="btn">
            Compare
          </Link>
          {hasActiveFilters && (
            <button type="button" className="btn" onClick={clearFilters}>
              Clear filters
            </button>
          )}
        </div>
      </div>

      {!loading && events.length === 0 && !queue && (
        <div className="alert alert-info" style={{ marginBottom: 16 }}>
          <strong>Get started:</strong> Open <Link to="/plant">Plant</Link>, build Substation →
          Voltage → Bay → Feeder → IED, then upload files on the IED.
        </div>
      )}

      {queue && (
        <div className="alert alert-info" style={{ marginBottom: 12 }}>
          Queue filter: <strong>{QUEUE_LABELS[queue] ?? queue}</strong>. Open an event, then use
          Overview / Consistency / Review as needed.
        </div>
      )}

      <div
        style={{
          marginBottom: 12,
          display: 'flex',
          flexWrap: 'wrap',
          gap: 10,
          alignItems: 'flex-end',
        }}
      >
        <div style={{ minWidth: 220, flex: '1 1 240px', maxWidth: 360 }}>
          <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            Search
          </label>
          <input
            className="form-control"
            placeholder="ID, station, bay, relay, fault…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            aria-label="Filter events"
          />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            From
          </label>
          <input
            type="datetime-local"
            className="form-control"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
          />
        </div>
        <div>
          <label style={{ display: 'block', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            To
          </label>
          <input
            type="datetime-local"
            className="form-control"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
          />
        </div>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', paddingBottom: 8 }}>
          {loading ? 'Loading…' : `${filtered.length} of ${events.length} events`}
        </div>
      </div>

      <div className="panel">
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Event ID</th>
                <th>Date/Time</th>
                <th>Location</th>
                <th>Relay</th>
                <th>Fault / element</th>
                <th>Status</th>
                <th>Sev</th>
                <th>DQ</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {!loading && filtered.length === 0 && (
                <tr>
                  <td
                    colSpan={9}
                    style={{ textAlign: 'center', padding: 28, color: 'var(--text-muted)' }}
                  >
                    {events.length === 0 ? (
                      <>
                        No disturbance events yet.{' '}
                        <Link to="/plant">Open Plant to add an IED and upload</Link>
                      </>
                    ) : (
                      <>
                        No events match the current filters.{' '}
                        <button type="button" className="btn btn-sm" onClick={clearFilters}>
                          Clear filters
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              )}
              {filtered.map((ev) => (
                <tr key={ev.id}>
                  <td>
                    <Link to={`/events/${ev.id}/summary`} className="mono">
                      {ev.event_id}
                    </Link>
                  </td>
                  <td className="num">
                    {ev.event_datetime
                      ? format(new Date(ev.event_datetime), 'yyyy-MM-dd HH:mm')
                      : '—'}
                  </td>
                  <td>
                    {ev.substation_name ??
                      (ev.extra as { substation_name?: string } | undefined)?.substation_name ??
                      '—'}
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      {ev.bay_name ??
                        (ev.extra as { bay_name?: string } | undefined)?.bay_name ??
                        ''}
                    </div>
                  </td>
                  <td className="mono">
                    {ev.relay_tag ??
                      (ev.extra as { relay_tag?: string } | undefined)?.relay_tag ??
                      '—'}
                  </td>
                  <td className="mono">
                    {ev.protection_summary || ev.fault_type || '—'}
                    {ev.protection_summary && ev.fault_type ? (
                      <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        {ev.fault_type}
                      </div>
                    ) : null}
                  </td>
                  <td>
                    <EventStatusCell event={ev} />
                  </td>
                  <td>
                    {ev.severity_summary ? (
                      <SeverityBadge severity={ev.severity_summary} />
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    {ev.data_quality ? (
                      <DataQualityBadge quality={ev.data_quality} />
                    ) : (
                      '—'
                    )}
                  </td>
                  <td>
                    <button
                      type="button"
                      className="btn btn-sm btn-danger"
                      disabled={deletingId === ev.id}
                      onClick={() => setPendingDelete(ev)}
                      title="Delete event"
                    >
                      {deletingId === ev.id ? 'Deleting…' : 'Delete'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <ConfirmDialog
        open={!!pendingDelete}
        title="Delete event?"
        message={`Delete event ${pendingDelete?.event_id}?\n\nThis removes the event and its analysis results from the database. The action is audited.`}
        confirmLabel="Delete"
        danger
        busy={!!deletingId}
        onCancel={() => setPendingDelete(null)}
        onConfirm={() => void onDelete()}
      />
    </div>
  );
}
