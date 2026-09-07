import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom';
import { format } from 'date-fns';
import { api } from '@/services/api';
import type { Event } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { SeverityBadge } from '@/components/SeverityBadge';
import { DataQualityBadge } from '@/components/DataQualityBadge';

const QUEUE_LABELS: Record<string, string> = {
  awaiting_analysis: 'Awaiting analysis',
  awaiting_review: 'Awaiting review',
  completed_reports: 'Completed reports',
  consistency_issues: 'Consistency issues',
  high_severity: 'High severity findings',
  rca_inconclusive: 'RCA inconclusive',
  parser_dq_issues: 'Parser / DQ issues',
};

export function EventsListPage() {
  const [events, setEvents] = useState<Event[]>([]);
  const [showCreate, setShowCreate] = useState(false);
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
      date_from?: string;
      date_to?: string;
    } = {};
    if (queue) params.queue = queue;
    if (dateFrom) params.date_from = new Date(dateFrom).toISOString();
    if (dateTo) params.date_to = new Date(dateTo).toISOString();
    void api
      .getEvents(Object.keys(params).length ? params : undefined)
      .then(setEvents)
      .finally(() => setLoading(false));
  }, [queue, dateFrom, dateTo]);

  useEffect(() => {
    const st = location.state as { openCreate?: boolean } | null;
    if (st?.openCreate) {
      navigate('/events/new', { replace: true });
    }
  }, [location.state, navigate]);

  const filtered = useMemo(() => {
    return events.filter((e) => {
      const q = filter.toLowerCase();
      if (!q) return true;
      return (
        e.event_id.toLowerCase().includes(q) ||
        (e.substation_name ?? '').toLowerCase().includes(q) ||
        (e.feeder ?? '').toLowerCase().includes(q) ||
        (e.description ?? '').toLowerCase().includes(q)
      );
    });
  }, [events, filter]);

  const [deletingId, setDeletingId] = useState<string | null>(null);

  const onDelete = async (ev: Event) => {
    const label = ev.event_id || ev.id;
    const ok = window.confirm(
      `Delete event ${label}?\n\nThis removes the event and its analysis results from the database. The action is audited. Original uploaded file blobs remain in storage (immutable).`,
    );
    if (!ok) return;
    setDeletingId(ev.id);
    try {
      await api.deleteEvent(ev.id);
      setEvents((prev) => prev.filter((e) => e.id !== ev.id));
    } catch (err) {
      window.alert(err instanceof Error ? err.message : 'Failed to delete event');
    } finally {
      setDeletingId(null);
    }
  };

  const onCreate = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    const created = await api.createEvent({
      event_id: String(fd.get('event_id') || '') || undefined,
      description: String(fd.get('description') || ''),
      feeder: String(fd.get('feeder') || ''),
      substation_name: String(fd.get('substation') || '') || 'UNKNOWN',
      bay_name: String(fd.get('bay') || '') || 'NOT VERIFIED',
      nominal_voltage_kv: Number(fd.get('voltage') || 0) || undefined,
      event_datetime: String(fd.get('datetime') || new Date().toISOString()),
    });
    setShowCreate(false);
    navigate(`/events/${created.id}/files`);
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Events</h1>
          <p className="subtitle">
            {queue && QUEUE_LABELS[queue]
              ? `Filtered: ${QUEUE_LABELS[queue]}`
              : 'Disturbance records pending analysis and review'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          {queue && (
            <button
              type="button"
              className="btn"
              onClick={() => setSearchParams({})}
            >
              Clear filter
            </button>
          )}
          <Link to="/events/new" className="btn btn-primary">
            + New event
          </Link>
          <button type="button" className="btn" onClick={() => setShowCreate(true)}>
            Quick create
          </button>
        </div>
      </div>

      {!loading && events.length === 0 && !queue && (
        <div className="alert alert-info" style={{ marginBottom: 16 }}>
          <strong>Get started:</strong> Create an event with plant context → upload COMTRADE CFG+DAT →
          Start analysis → follow the recommended next-step banner. Prefer{' '}
          <Link to="/events/new">New event</Link> over Quick upload when you know the feeder/relay.
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
        <div style={{ maxWidth: 280, flex: 1 }}>
          <input
            className="form-control"
            placeholder="Filter by ID, station, feeder…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
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
        {(dateFrom || dateTo) && (
          <button
            type="button"
            className="btn btn-sm"
            onClick={() => {
              setDateFrom('');
              setDateTo('');
            }}
          >
            Clear dates
          </button>
        )}
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
                <th>Fault</th>
                <th>Status</th>
                <th>Sev</th>
                <th>DQ</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {!loading && filtered.length === 0 && (
                <tr>
                  <td colSpan={9} style={{ textAlign: 'center', padding: 28, color: 'var(--text-muted)' }}>
                    No disturbance events yet.{' '}
                    <Link to="/events/new">Create your first event</Link>
                  </td>
                </tr>
              )}
              {filtered.map((ev) => (
                <tr key={ev.id}>
                  <td>
                    <Link to={`/events/${ev.id}/overview`} className="mono">
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
                  <td className="mono">{ev.fault_type ?? '—'}</td>
                  <td>
                    <StatusBadge status={ev.status} />
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
                      onClick={() => void onDelete(ev)}
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

      {showCreate && (
        <div className="modal-backdrop" onClick={() => setShowCreate(false)}>
          <div
            className="modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-labelledby="create-event-title"
          >
            <div className="modal-header">
              <h2 id="create-event-title">Quick create</h2>
              <button
                type="button"
                className="btn btn-sm btn-ghost"
                onClick={() => setShowCreate(false)}
              >
                ✕
              </button>
            </div>
            <form onSubmit={onCreate}>
              <div className="modal-body">
                <div className="form-group">
                  <label htmlFor="event_id">Event ID (optional)</label>
                  <input
                    id="event_id"
                    name="event_id"
                    className="form-control"
                    placeholder="Auto if blank"
                  />
                </div>
                <div className="two-col">
                  <div className="form-group">
                    <label htmlFor="substation">Substation</label>
                    <input
                      id="substation"
                      name="substation"
                      className="form-control"
                      placeholder="UNKNOWN"
                    />
                  </div>
                  <div className="form-group">
                    <label htmlFor="bay">Bay</label>
                    <input id="bay" name="bay" className="form-control" placeholder="NOT VERIFIED" />
                  </div>
                </div>
                <div className="two-col">
                  <div className="form-group">
                    <label htmlFor="feeder">Feeder</label>
                    <input id="feeder" name="feeder" className="form-control" />
                  </div>
                  <div className="form-group">
                    <label htmlFor="voltage">Nominal kV</label>
                    <input
                      id="voltage"
                      name="voltage"
                      type="number"
                      step="0.1"
                      className="form-control"
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label htmlFor="datetime">Event datetime (ISO)</label>
                  <input
                    id="datetime"
                    name="datetime"
                    className="form-control"
                    defaultValue={new Date().toISOString().slice(0, 19)}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="description">Description</label>
                  <textarea id="description" name="description" className="form-control" rows={3} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn" onClick={() => setShowCreate(false)}>
                  Cancel
                </button>
                <Link to="/events/new" className="btn">
                  Full wizard
                </Link>
                <button type="submit" className="btn btn-primary">
                  Create & upload files
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
