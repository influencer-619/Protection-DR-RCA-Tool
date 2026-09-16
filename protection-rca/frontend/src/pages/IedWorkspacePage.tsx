import { useCallback, useEffect, useState, type DragEvent, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { format } from 'date-fns';
import { api } from '@/services/api';
import type { Event, IedContext } from '@/types';
import { EventStatusCell } from '@/components/EventStatusCell';
import { UPLOAD_ACCEPT, UPLOAD_ACCEPT_HINT } from '@/utils/uploadAccept';
import styles from './IedWorkspacePage.module.css';

function packageReady(names: string[]): boolean {
  const lower = names.map((n) => n.toLowerCase());
  const hasCff = lower.some((n) => n.endsWith('.cff'));
  const hasCfg = lower.some((n) => n.endsWith('.cfg'));
  const hasDat = lower.some((n) => n.endsWith('.dat'));
  const hasSettings = lower.some(
    (n) =>
      n.includes('setting') ||
      n.endsWith('.set') ||
      n.endsWith('.xrio') ||
      n.endsWith('.rio') ||
      (n.endsWith('.json') && (n.includes('param') || n.includes('relay'))),
  );
  return (hasCff || (hasCfg && hasDat)) && hasSettings;
}

export function IedWorkspacePage() {
  const { iedId } = useParams<{ iedId: string }>();
  const navigate = useNavigate();
  const [ctx, setCtx] = useState<IedContext | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [description, setDescription] = useState('');

  const load = useCallback(async () => {
    if (!iedId) return;
    setLoading(true);
    setError(null);
    try {
      const [context, evs] = await Promise.all([
        api.getIedContext(iedId),
        api.getEvents({ relay_id: iedId }),
      ]);
      setCtx(context);
      setEvents(evs);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load IED');
    } finally {
      setLoading(false);
    }
  }, [iedId]);

  useEffect(() => {
    void load();
  }, [load]);

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    setFiles((prev) => [...prev, ...Array.from(e.dataTransfer.files)]);
  };

  const onUploadAnalyse = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!iedId || !files.length) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createEvent({
        relay_id: iedId,
        description: description.trim() || undefined,
        event_datetime: new Date().toISOString(),
      });
      await api.uploadEventFiles(created.id, files);
      const names = files.map((f) => f.name);
      if (packageReady(names)) {
        try {
          await api.startAnalysis(created.id, true);
        } catch {
          /* navigate anyway; user can start analysis from event */
        }
      }
      setFiles([]);
      setDescription('');
      navigate(`/events/${created.id}/files`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <p className={styles.muted}>Loading IED…</p>;
  if (!ctx) {
    return (
      <div>
        <p className={styles.error}>{error || 'IED not found'}</p>
        <Link to="/plant">Back to Plant</Link>
      </div>
    );
  }

  return (
    <div className={`page ${styles.page}`}>
      <nav className={styles.crumb}>
        <Link to="/plant">Plant</Link>
        <span>/</span>
        <span>{ctx.path_label}</span>
      </nav>

      <header className={styles.header}>
        <div>
          <h1>{ctx.ied.name}</h1>
          <p className={styles.sub}>
            Tag <span className="mono">{ctx.ied.relay_tag}</span>
            {ctx.voltage_level?.nominal_voltage_kv != null && (
              <> · {ctx.voltage_level.nominal_voltage_kv} kV</>
            )}
          </p>
        </div>
        <Link to="/plant" className="btn btn-sm">
          Plant tree
        </Link>
      </header>

      {error && <div className={styles.error}>{error}</div>}

      <section className={styles.panel}>
        <h2>Upload for analysis</h2>
        <p className={styles.hint}>
          Files are attached to a new event under this IED. {UPLOAD_ACCEPT_HINT}
        </p>
        <form onSubmit={(ev) => void onUploadAnalyse(ev)}>
          <input
            className={styles.desc}
            placeholder="Optional description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <div
            className={`${styles.drop} ${dragging ? styles.dragging : ''}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <p>Drop COMTRADE / settings / SOE here, or choose files</p>
            <input
              type="file"
              multiple
              accept={UPLOAD_ACCEPT}
              onChange={(e) => {
                if (e.target.files?.length) {
                  setFiles((prev) => [...prev, ...Array.from(e.target.files!)]);
                }
              }}
            />
          </div>
          {files.length > 0 && (
            <ul className={styles.fileList}>
              {files.map((f) => (
                <li key={`${f.name}-${f.size}`}>{f.name}</li>
              ))}
            </ul>
          )}
          <div className={styles.actions}>
            <button type="submit" className="btn" disabled={busy || !files.length}>
              {busy ? 'Creating…' : 'Upload & create event'}
            </button>
            {files.length > 0 && (
              <button type="button" className="btn btn-sm" onClick={() => setFiles([])}>
                Clear files
              </button>
            )}
          </div>
        </form>
      </section>

      <section className={styles.panel}>
        <h2>Events on this IED</h2>
        {events.length === 0 ? (
          <p className={styles.muted}>No events yet. Upload files above to start analysis.</p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>Event</th>
                <th>Status</th>
                <th>Element</th>
                <th>When</th>
              </tr>
            </thead>
            <tbody>
              {events.map((ev) => (
                <tr key={ev.id}>
                  <td>
                    <Link to={`/events/${ev.id}/summary`}>{ev.event_id}</Link>
                    {ev.description && (
                      <div className={styles.rowSub}>{ev.description}</div>
                    )}
                  </td>
                  <td>
                    <EventStatusCell event={ev} />
                  </td>
                  <td className="mono">
                    {ev.protection_summary || ev.fault_type || '—'}
                    {ev.protection_summary && ev.fault_type ? (
                      <div className={styles.rowSub}>{ev.fault_type}</div>
                    ) : null}
                  </td>
                  <td className="mono">
                    {ev.event_datetime
                      ? format(new Date(ev.event_datetime), 'yyyy-MM-dd HH:mm')
                      : format(new Date(ev.created_at), 'yyyy-MM-dd HH:mm')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
