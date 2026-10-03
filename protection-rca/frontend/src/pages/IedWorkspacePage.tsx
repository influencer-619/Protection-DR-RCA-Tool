import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { api } from '@/services/api';
import type { Event, IedContext, Iec61850FetchResult } from '@/types';
import { EventStatusCell } from '@/components/EventStatusCell';
import { Iec61850FetchPanel } from '@/components/Iec61850FetchPanel';
import { UPLOAD_ACCEPT, UPLOAD_ACCEPT_HINT, hasComtradePackage } from '@/utils/uploadAccept';
import styles from './IedWorkspacePage.module.css';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function eventTime(ev: Event): Date {
  return new Date(ev.event_datetime || ev.created_at);
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
  const [source, setSource] = useState<'iec61850' | 'manual'>('iec61850');
  const fileInput = useRef<HTMLInputElement>(null);

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

  const refreshEvents = useCallback(() => {
    if (!iedId) return;
    api
      .getEvents({ relay_id: iedId })
      .then(setEvents)
      .catch(() => undefined);
  }, [iedId]);

  const addFiles = (list: FileList | File[]) => {
    const incoming = Array.from(list);
    setFiles((prev) => {
      const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
      return [...prev, ...incoming.filter((f) => !seen.has(`${f.name}:${f.size}`))];
    });
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
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
      // COMTRADE present → run full pipeline, then land on one-page summary
      if (hasComtradePackage(names)) {
        try {
          await api.startAnalysis(created.id, true);
        } catch {
          /* still open summary; user can re-run analysis from the event header */
        }
        setFiles([]);
        setDescription('');
        navigate(`/events/${created.id}/summary`);
        return;
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

  const onFetched = async (result: Iec61850FetchResult) => {
    await Promise.all(
      result.events
        .filter((ev) => ev.package_ready)
        .map((ev) => api.startAnalysis(ev.id, true).catch(() => undefined)),
    );
    if (result.events.length === 1) {
      navigate(`/events/${result.events[0].id}/summary`);
    } else {
      void load();
    }
  };

  const stats = useMemo(() => {
    const sorted = [...events].sort((a, b) => eventTime(b).getTime() - eventTime(a).getTime());
    const review = events.filter((e) => (e.status || '').toUpperCase() === 'REVIEW').length;
    return { total: events.length, latest: sorted[0], review, sorted };
  }, [events]);

  if (loading) return <p className={`page ${styles.muted}`}>Loading IED…</p>;
  if (!ctx) {
    return (
      <div className="page">
        <p className={styles.error}>{error || 'IED not found'}</p>
        <Link to="/plant">Back to Plant</Link>
      </div>
    );
  }

  const pathParts = [
    ctx.substation?.name,
    ctx.voltage_level?.name,
    ctx.bay?.name,
    ctx.feeder?.name,
  ].filter(Boolean) as string[];

  return (
    <div className={`page ${styles.page}`}>
      <header className={styles.hero}>
        <div className={styles.heroIcon} aria-hidden="true">
          <svg viewBox="0 0 24 24">
            <rect x="5" y="3" width="14" height="18" rx="2" />
            <path d="M9 7h6M9 11h6" />
            <circle cx="12" cy="16" r="1.5" />
          </svg>
        </div>
        <div className={styles.heroMain}>
          <nav className={styles.path} aria-label="Plant location">
            <Link to="/plant">Plant</Link>
            {pathParts.map((p, i) => (
              <span key={`${p}-${i}`} className={styles.pathPart}>
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M9 6l6 6-6 6" />
                </svg>
                {p}
              </span>
            ))}
          </nav>
          <h1>{ctx.ied.name}</h1>
          <div className={styles.chips}>
            <span className={styles.chip}>
              Tag <span className="mono">{ctx.ied.relay_tag}</span>
            </span>
            {ctx.voltage_level?.nominal_voltage_kv != null && (
              <span className={`${styles.chip} ${styles.chipKv}`}>
                {ctx.voltage_level.nominal_voltage_kv} kV
              </span>
            )}
            {ctx.ied.ip_address && (
              <span className={styles.chip}>
                IP <span className="mono">{ctx.ied.ip_address}</span>
              </span>
            )}
          </div>
        </div>
        <div className={styles.heroStats}>
          <div className={styles.stat}>
            <span className={styles.statVal}>{stats.total}</span>
            <span className={styles.statLbl}>Events</span>
          </div>
          <div className={styles.stat}>
            <span className={`${styles.statVal} ${stats.review ? styles.statWarn : ''}`}>
              {stats.review}
            </span>
            <span className={styles.statLbl}>In review</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statValSm}>
              {stats.latest ? formatDistanceToNow(eventTime(stats.latest), { addSuffix: true }) : '—'}
            </span>
            <span className={styles.statLbl}>Last event</span>
          </div>
        </div>
      </header>

      {error && <div className={styles.error}>{error}</div>}

      <div className={styles.grid}>
        <section className={styles.panel}>
          <div className={styles.panelHead}>
            <div>
              <h2>Acquire data for analysis</h2>
              <p className={styles.panelSub}>
                Each disturbance record becomes an event under this IED.
              </p>
            </div>
            <div className={styles.segment} role="tablist">
              <button
                type="button"
                role="tab"
                aria-selected={source === 'iec61850'}
                className={source === 'iec61850' ? styles.segActive : styles.seg}
                onClick={() => setSource('iec61850')}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M5 12.5a10 10 0 0114 0M8 15.5a5.5 5.5 0 018 0" />
                  <circle cx="12" cy="19" r="1.2" />
                </svg>
                Fetch from IED
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={source === 'manual'}
                className={source === 'manual' ? styles.segActive : styles.seg}
                onClick={() => setSource('manual')}
              >
                <svg viewBox="0 0 24 24" aria-hidden="true">
                  <path d="M12 16V4M7 9l5-5 5 5" />
                  <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
                </svg>
                Manual upload
              </button>
            </div>
          </div>

          <div className={styles.panelBody}>
            {source === 'iec61850' ? (
              <Iec61850FetchPanel
                iedId={iedId!}
                onFetched={(r) => void onFetched(r)}
                onAutoFetched={refreshEvents}
              />
            ) : (
              <form className={styles.upload} onSubmit={(ev) => void onUploadAnalyse(ev)}>
                <div
                  className={`${styles.drop} ${dragging ? styles.dragging : ''}`}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={onDrop}
                  onClick={() => fileInput.current?.click()}
                  role="button"
                  tabIndex={0}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') fileInput.current?.click();
                  }}
                >
                  <div className={styles.dropIcon} aria-hidden="true">
                    <svg viewBox="0 0 24 24">
                      <path d="M12 16V4M7 9l5-5 5 5" />
                      <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
                    </svg>
                  </div>
                  <strong>Drop COMTRADE, settings and SOE files here</strong>
                  <span>
                    or <span className={styles.linkish}>browse your computer</span>
                  </span>
                  <span className={styles.dropHint}>{UPLOAD_ACCEPT_HINT}</span>
                  <input
                    ref={fileInput}
                    type="file"
                    multiple
                    hidden
                    accept={UPLOAD_ACCEPT}
                    onChange={(e) => {
                      if (e.target.files?.length) addFiles(e.target.files);
                      e.target.value = '';
                    }}
                  />
                </div>

                {files.length > 0 && (
                  <ul className={styles.fileList}>
                    {files.map((f) => (
                      <li key={`${f.name}-${f.size}`} className={styles.fileChip}>
                        <span className={styles.fileExt}>{f.name.split('.').pop()?.toUpperCase()}</span>
                        <span className={styles.fileName} title={f.name}>
                          {f.name}
                        </span>
                        <span className={styles.fileSize}>{formatSize(f.size)}</span>
                        <button
                          type="button"
                          className={styles.fileRemove}
                          onClick={() => setFiles((prev) => prev.filter((x) => x !== f))}
                          aria-label={`Remove ${f.name}`}
                        >
                          ×
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                <input
                  className="form-control"
                  placeholder="Optional description (e.g. trip on 12 Sep, B-phase)"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />

                <div className={styles.actions}>
                  <button type="submit" className="btn btn-primary" disabled={busy || !files.length}>
                    {busy
                      ? 'Uploading & analysing…'
                      : hasComtradePackage(files.map((f) => f.name))
                        ? 'Upload, analyse & open summary'
                        : 'Upload & create event'}
                  </button>
                  {files.length > 0 && (
                    <button type="button" className="btn" onClick={() => setFiles([])}>
                      Clear {files.length} file{files.length === 1 ? '' : 's'}
                    </button>
                  )}
                  {files.length > 0 && !hasComtradePackage(files.map((f) => f.name)) && (
                    <span className={styles.note}>
                      Add CFG + DAT (or CFF) and a settings file to start analysis automatically.
                    </span>
                  )}
                </div>
              </form>
            )}
          </div>
        </section>

        <section className={`${styles.panel} ${styles.eventsPanel}`}>
          <div className={styles.panelHead}>
            <div>
              <h2>Events on this IED</h2>
              <p className={styles.panelSub}>
                {stats.total} event{stats.total === 1 ? '' : 's'} · newest first
              </p>
            </div>
          </div>
          {events.length === 0 ? (
            <div className={styles.emptyEvents}>
              <div className={styles.emptyIcon} aria-hidden="true">
                <svg viewBox="0 0 24 24">
                  <path d="M3 12h4l2-6 4 12 2-6h6" />
                </svg>
              </div>
              <strong>No events yet</strong>
              <p>Fetch from the IED or upload files to create the first event.</p>
            </div>
          ) : (
            <ul className={styles.eventList}>
              {stats.sorted.map((ev) => (
                <li key={ev.id}>
                  <Link to={`/events/${ev.id}/summary`} className={styles.eventRow}>
                    <div className={styles.eventTop}>
                      <span className={styles.eventNo}>{ev.event_id}</span>
                      <EventStatusCell event={ev} />
                    </div>
                    <div className={styles.eventMeta}>
                      <span className="mono">{format(eventTime(ev), 'yyyy-MM-dd HH:mm')}</span>
                      {(ev.protection_summary || ev.fault_type) && (
                        <span className={styles.eventElem}>
                          {[ev.protection_summary, ev.fault_type].filter(Boolean).join(' · ')}
                        </span>
                      )}
                    </div>
                    {ev.description && <div className={styles.eventDesc}>{ev.description}</div>}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
