import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type Dispatch,
  type DragEvent,
  type FormEvent,
  type Ref,
  type SetStateAction,
} from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { format, formatDistanceToNow } from 'date-fns';
import { api } from '@/services/api';
import type { Event, IedContext, Iec61850FetchResult } from '@/types';
import { EventStatusCell } from '@/components/EventStatusCell';
import { Iec61850FetchPanel } from '@/components/Iec61850FetchPanel';
import {
  UPLOAD_ACCEPT,
  UPLOAD_ACCEPT_HINT,
  collectDroppedFiles,
  filterAllowedUploads,
  hasComtradePackage,
} from '@/utils/uploadAccept';
import { formatDrDate, parseApiDate, parseDrDate } from '@/utils/dateTime';
import styles from './IedWorkspacePage.module.css';

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function eventTime(ev: Event): Date {
  if (ev.event_datetime) return parseDrDate(ev.event_datetime) ?? new Date(0);
  return parseApiDate(ev.created_at) ?? new Date(0);
}

function mergeFiles(prev: File[], list: FileList | File[]): File[] {
  const seen = new Set(prev.map((f) => `${f.name}:${f.size}`));
  const next = filterAllowedUploads(Array.from(list)).filter(
    (f) => !seen.has(`${f.name}:${f.size}`),
  );
  return [...prev, ...next];
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
  const [dropNote, setDropNote] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const uid = useId();

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

  const onUpload = async (e?: FormEvent, andAnalyse = false) => {
    e?.preventDefault();
    if (!iedId || !files.length) return;
    setBusy(true);
    setError(null);
    try {
      const created = await api.createEvent({
        relay_id: iedId,
        description: description.trim() || undefined,
      });
      await api.uploadEventFiles(created.id, files, { end_label: 'LOCAL' });
      const names = files.map((f) => f.name);
      setFiles([]);
      setDescription('');
      void load();
      if (andAnalyse && hasComtradePackage(names)) {
        try {
          await api.startAnalysis(created.id, true);
        } catch {
          /* open summary anyway */
        }
        navigate(`/events/${created.id}/summary`);
        return;
      }
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

  const renderDropZone = (
    zoneFiles: File[],
    setZoneFiles: Dispatch<SetStateAction<File[]>>,
    isDragging: boolean,
    setIsDragging: (v: boolean) => void,
    fileInputRef: Ref<HTMLInputElement>,
    folderInputRef: Ref<HTMLInputElement>,
  ) => {
    const fileInputId = `${uid}-files`;
    const folderEl = () =>
      typeof folderInputRef === 'object' && folderInputRef && 'current' in folderInputRef
        ? folderInputRef.current
        : null;
    const addFromList = (list: FileList | File[] | null | undefined) => {
      if (!list || !list.length) {
        setDropNote('No allowed files found. Drop CFG/DAT (or a folder), or Browse / Add folder…');
        return;
      }
      const incoming = filterAllowedUploads(Array.from(list));
      if (!incoming.length) {
        setDropNote('No allowed file types in that selection.');
        return;
      }
      setDropNote(null);
      setZoneFiles((prev) => mergeFiles(prev, incoming));
    };
    const onDrop = (ev: DragEvent) => {
      ev.preventDefault();
      ev.stopPropagation();
      setIsDragging(false);
      void collectDroppedFiles(ev.dataTransfer).then(addFromList);
    };
    return (
      <div className={styles.zone}>
        <div className={styles.zoneHead}>
          <strong>{ctx?.ied.name ?? 'IED'}</strong>
        </div>
        <label
          className={`${styles.drop} ${isDragging ? styles.dragging : ''}`}
          onDragEnter={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragOver={(e) => {
            e.preventDefault();
            setIsDragging(true);
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            setIsDragging(false);
          }}
          onDrop={onDrop}
        >
          <div className={styles.dropIcon} aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M12 16V4M7 9l5-5 5 5" />
              <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
            </svg>
          </div>
          <strong>Drop files or folder here</strong>
          <span>
            or <span className={styles.linkish}>browse files</span>
          </span>
          <span className={styles.dropHint}>{UPLOAD_ACCEPT_HINT}</span>
          <input
            id={fileInputId}
            ref={fileInputRef}
            type="file"
            multiple
            className={styles.fileInput}
            accept={UPLOAD_ACCEPT}
            onChange={(e) => {
              addFromList(e.target.files);
              e.target.value = '';
            }}
          />
        </label>
        <div className={styles.dropActions}>
          <button type="button" className="btn btn-sm" onClick={() => folderEl()?.click()}>
            Add folder…
          </button>
          <input
            ref={folderInputRef}
            type="file"
            multiple
            className={styles.fileInput}
            {...({ webkitdirectory: '', directory: '' } as Record<string, string>)}
            onChange={(e) => {
              addFromList(e.target.files);
              e.target.value = '';
            }}
          />
        </div>
        {zoneFiles.length > 0 && (
          <ul className={styles.fileList}>
            {zoneFiles.map((f) => (
              <li key={`${f.name}-${f.size}`} className={styles.fileChip}>
                <span className={styles.fileExt}>{f.name.split('.').pop()?.toUpperCase()}</span>
                <span className={styles.fileName} title={f.name}>
                  {f.name}
                </span>
                <span className={styles.fileSize}>{formatSize(f.size)}</span>
                <button
                  type="button"
                  className={styles.fileRemove}
                  onClick={() => setZoneFiles((prev) => prev.filter((x) => x !== f))}
                  aria-label={`Remove ${f.name}`}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  };

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
          <p className={styles.panelSub} style={{ marginTop: 8 }}>
            Fault analysis for this IED — upload or fetch disturbance records, then open an
            event to run analysis.
          </p>
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
              <p className={styles.panelSub}>Fetch or upload DRs for this IED only</p>
            </div>
            <div className={styles.segment} role="tablist" aria-label="Acquire source">
              <button
                type="button"
                role="tab"
                aria-selected={source === 'iec61850'}
                className={source === 'iec61850' ? styles.segActive : styles.seg}
                onClick={() => setSource('iec61850')}
              >
                Fetch from IED
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={source === 'manual'}
                className={source === 'manual' ? styles.segActive : styles.seg}
                onClick={() => setSource('manual')}
              >
                Manual upload
              </button>
            </div>
          </div>
          <div className={styles.panelBody}>
            {source === 'iec61850' ? (
              <Iec61850FetchPanel
                iedId={ctx.ied.id}
                onFetched={(r) => void onFetched(r)}
                onAutoFetched={refreshEvents}
              />
            ) : (
              <form className={styles.upload} onSubmit={(ev) => void onUpload(ev, false)}>
                {renderDropZone(files, setFiles, dragging, setDragging, fileInput, folderInput)}
                {dropNote && <p className={styles.dropNote}>{dropNote}</p>}
                <input
                  className="form-control"
                  placeholder="Optional description (e.g. trip on 12 Sep, B-phase)"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
                <div className={styles.actions}>
                  <button type="submit" className="btn btn-primary" disabled={busy || !files.length}>
                    {busy ? 'Uploading…' : 'Upload & create event'}
                  </button>
                  {hasComtradePackage(files.map((f) => f.name)) && (
                    <button
                      type="button"
                      className="btn"
                      disabled={busy || !files.length}
                      onClick={() => void onUpload(undefined, true)}
                    >
                      Upload, analyse &amp; open summary
                    </button>
                  )}
                  {files.length > 0 && (
                    <button
                      type="button"
                      className="btn"
                      onClick={() => {
                        setFiles([]);
                        setDropNote(null);
                      }}
                    >
                      Clear {files.length} file{files.length === 1 ? '' : 's'}
                    </button>
                  )}
                </div>
              </form>
            )}
          </div>
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHead}>
            <div>
              <h2>Events on this IED</h2>
              <p className={styles.panelSub}>Newest first</p>
            </div>
          </div>
          <div className={styles.panelBody}>
            {stats.sorted.length === 0 ? (
              <p className={styles.muted}>
                No events yet. Fetch from the IED or upload files to create the first event.
              </p>
            ) : (
              <ul className={styles.eventList}>
                {stats.sorted.map((ev) => (
                  <li key={ev.id}>
                    <Link to={`/events/${ev.id}/summary`} className={styles.eventRow}>
                      <div>
                        <span className="mono">{ev.event_id}</span>
                        <span className={styles.eventWhen}>
                          {formatDrDate(ev.event_datetime) ||
                            (parseApiDate(ev.created_at)
                              ? format(parseApiDate(ev.created_at)!, 'dd MMM yyyy HH:mm')
                              : '—')}
                        </span>
                      </div>
                      <EventStatusCell event={ev} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
