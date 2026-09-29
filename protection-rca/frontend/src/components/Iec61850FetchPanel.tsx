import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { format } from 'date-fns';
import { api } from '@/services/api';
import type {
  Iec61850Browse,
  Iec61850FetchResult,
  Iec61850Identify,
  Iec61850Info,
  Iec61850Nameplate,
} from '@/types';
import { Iec61850AutoFetchCard } from './Iec61850AutoFetchCard';
import styles from './Iec61850FetchPanel.module.css';

interface Props {
  iedId: string;
  onFetched: (result: Iec61850FetchResult) => void;
  onAutoFetched: () => void;
}

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} kB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatWhen(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : format(d, 'yyyy-MM-dd HH:mm:ss');
}

function nameplateLabel(np?: Iec61850Nameplate | null): string {
  if (!np) return '';
  const parts = [np.vendor, np.model].filter(Boolean).join(' ');
  const extra = [np.swRev && `fw ${np.swRev}`, np.serNum && `S/N ${np.serNum}`].filter(Boolean);
  return [parts, ...extra].filter(Boolean).join(' · ');
}

export function Iec61850FetchPanel({ iedId, onFetched, onAutoFetched }: Props) {
  const [info, setInfo] = useState<Iec61850Info | null>(null);
  const [host, setHost] = useState('');
  const [port, setPort] = useState('102');
  const [vendor, setVendor] = useState('AUTO');
  const [identity, setIdentity] = useState<Iec61850Identify | null>(null);
  const [browse, setBrowse] = useState<Iec61850Browse | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [includeSettings, setIncludeSettings] = useState(true);
  const [includeEvents, setIncludeEvents] = useState(true);
  const [includeScl, setIncludeScl] = useState(false);
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState<null | 'test' | 'browse' | 'fetch'>(null);
  const [error, setError] = useState<string | null>(null);
  const [warnings, setWarnings] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    void Promise.all([api.getIec61850Info(), api.getIec61850Connection(iedId)])
      .then(([i, c]) => {
        if (cancelled) return;
        setInfo(i);
        setHost(c.host || '');
        setPort(String(c.port || 102));
        setVendor(c.vendor_profile || 'AUTO');
      })
      .catch(() => {
        /* panel still usable; errors surface on actions */
      });
    return () => {
      cancelled = true;
    };
  }, [iedId]);

  const conn = () => ({
    host: host.trim(),
    port: Number(port) || 102,
    vendor_profile: vendor,
  });

  const validHost = host.trim().length > 0;
  const libraryMissing = info != null && !info.library.available;
  const vendorInfo = info?.vendors.find((v) => v.id === vendor);

  const onTest = async () => {
    setBusy('test');
    setError(null);
    try {
      setIdentity(await api.testIec61850(iedId, conn()));
    } catch (e) {
      setIdentity(null);
      setError(e instanceof Error ? e.message : 'Connection test failed');
    } finally {
      setBusy(null);
    }
  };

  const onBrowse = async () => {
    setBusy('browse');
    setError(null);
    setWarnings([]);
    try {
      const res = await api.browseIec61850(iedId, conn());
      setBrowse(res);
      const newest = res.records.find((r) => r.complete && !r.event_id);
      setSelected(newest ? new Set([newest.key]) : new Set());
    } catch (e) {
      setBrowse(null);
      setError(e instanceof Error ? e.message : 'Could not browse the IED');
    } finally {
      setBusy(null);
    }
  };

  const onFetch = async () => {
    setBusy('fetch');
    setError(null);
    setWarnings([]);
    try {
      const res = await api.fetchIec61850(iedId, {
        ...conn(),
        records: Array.from(selected),
        include_settings: includeSettings,
        include_events: includeEvents,
        include_scl: includeScl,
        description: description.trim() || undefined,
      });
      setWarnings(res.warnings);
      setDescription('');
      onFetched(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Fetch from IED failed');
    } finally {
      setBusy(null);
    }
  };

  const toggle = (key: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });

  const extraCounts = useMemo(() => {
    if (!browse) return null;
    return {
      settings: browse.settings_files.length,
      events: browse.event_files.length,
      scl: browse.scl_files.length,
    };
  }, [browse]);

  const canFetch =
    validHost && !busy && (selected.size > 0 || includeSettings || includeEvents || includeScl);

  return (
    <div className={styles.wrap}>
      <p className={styles.hint}>
        <span className={styles.readOnly}>Read-only</span>
        Pulls disturbance records (COMTRADE), settings and event files straight from the relay using
        IEC 61850 MMS file transfer and data-model reads. Nothing is written to the IED.
      </p>

      {libraryMissing && (
        <div className={styles.warn}>
          IEC 61850 client library is not installed on the server
          (<span className="mono">pip install pyiec61850-ng</span>). Use manual upload meanwhile.
        </div>
      )}

      <section className={styles.block}>
        <div className={styles.blockHead}>
          <span className={styles.blockNum}>1</span>
          <div>
            <h3>Relay connection</h3>
            <p>IP address of the relay’s IEC 61850 (MMS) interface. Port is normally 102.</p>
          </div>
        </div>
        <div className={styles.connRow}>
          <label className={styles.field}>
            <span>IP address</span>
            <input
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="e.g. 192.168.10.21"
              className="mono"
            />
          </label>
          <label className={`${styles.field} ${styles.port}`}>
            <span>Port</span>
            <input
              value={port}
              onChange={(e) => setPort(e.target.value.replace(/[^0-9]/g, ''))}
              inputMode="numeric"
              className="mono"
            />
          </label>
          <label className={`${styles.field} ${styles.vendor}`}>
            <span>Vendor</span>
            <select value={vendor} onChange={(e) => setVendor(e.target.value)}>
              {(info?.vendors ?? [{ id: 'AUTO', label: 'Auto-detect', families: '', notes: '' }]).map(
                (v) => (
                  <option key={v.id} value={v.id}>
                    {v.label}
                  </option>
                ),
              )}
            </select>
          </label>
          <div className={styles.connActions}>
            <button
              type="button"
              className="btn btn-sm"
              disabled={!validHost || !!busy || libraryMissing}
              onClick={() => void onTest()}
            >
              {busy === 'test' ? 'Connecting…' : 'Test connection'}
            </button>
          </div>
        </div>
        {vendorInfo && vendorInfo.id !== 'AUTO' && (
          <p className={styles.vendorNote}>
            {vendorInfo.families}
            {vendorInfo.notes ? ` — ${vendorInfo.notes}` : ''}
          </p>
        )}

        {error && <div className={styles.error}>{error}</div>}

        {identity && (
          <div className={styles.ok}>
            Connected to <span className="mono">{identity.host}:{identity.port}</span>
            {nameplateLabel(identity.nameplate) && <> · {nameplateLabel(identity.nameplate)}</>} ·
            profile {identity.detected_profile_label} · {identity.logical_devices.length} logical
            device(s) · file services {identity.file_service ? 'available' : 'NOT available'} ·{' '}
            {identity.elapsed_ms} ms
            {!identity.file_service && identity.file_service_error && (
              <div className={styles.sub}>{identity.file_service_error}</div>
            )}
          </div>
        )}
      </section>

      <section className={styles.block}>
        <div className={styles.blockHead}>
          <span className={styles.blockNum}>2</span>
          <div>
            <h3>Automatic fetch</h3>
            <p>Let the server watch this relay and create events for new records by itself.</p>
          </div>
        </div>
        <Iec61850AutoFetchCard
          iedId={iedId}
          connection={conn}
          disabled={libraryMissing}
          onNewEvents={onAutoFetched}
        />
      </section>

      <section className={styles.block}>
        <div className={styles.blockHead}>
          <span className={styles.blockNum}>3</span>
          <div>
            <h3>Fetch now</h3>
            <p>Browse the relay, pick records and create events immediately.</p>
          </div>
          <button
            type="button"
            className={`btn btn-sm ${styles.blockAction}`}
            disabled={!validHost || !!busy || libraryMissing}
            onClick={() => void onBrowse()}
          >
            {busy === 'browse' ? 'Browsing…' : browse ? 'Refresh list' : 'Browse IED'}
          </button>
        </div>

        {browse && (
          <>
            <div className={styles.browseHead}>
              <strong>{browse.records.length}</strong> disturbance record(s) on{' '}
              {nameplateLabel(browse.nameplate) || 'IED'} ({browse.profile_label})
              {browse.truncated && <span className={styles.sub}> — listing truncated (time limit)</span>}
            </div>
            {browse.records.length === 0 ? (
              <p className={styles.muted}>
                No COMTRADE records found in the IED file store. Check that MMS file transfer is
                enabled in the relay configuration tool, or pick the vendor explicitly.
              </p>
            ) : (
              <div className={styles.tableWrap}>
                <table className={styles.table}>
                  <thead>
                    <tr>
                      <th />
                      <th>Record</th>
                      <th>Recorded</th>
                      <th>Files</th>
                      <th>Size</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {browse.records.map((r) => (
                      <tr key={r.key} className={selected.has(r.key) ? styles.selectedRow : undefined}>
                        <td>
                          <input
                            type="checkbox"
                            checked={selected.has(r.key)}
                            onChange={() => toggle(r.key)}
                            aria-label={`Select ${r.name}`}
                          />
                        </td>
                        <td>
                          <span className="mono">{r.name}</span>
                          <div className={styles.sub}>{r.directory}</div>
                        </td>
                        <td className="mono">{formatWhen(r.last_modified)}</td>
                        <td className="mono" title={r.files.join('\n')}>
                          {r.files.map((f) => f.split('.').pop()?.toUpperCase()).join(' + ')}
                        </td>
                        <td className="mono">{formatSize(r.size)}</td>
                        <td>
                          {r.event_id ? (
                            <Link to={`/events/${r.event_id}/summary`}>Already fetched</Link>
                          ) : r.complete ? (
                            'Complete'
                          ) : (
                            <span className={styles.sub}>Incomplete (CFG/DAT missing)</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        <div className={styles.options}>
          <label>
            <input
              type="checkbox"
              checked={includeSettings}
              onChange={(e) => setIncludeSettings(e.target.checked)}
            />{' '}
            {`Settings (read from data model${extraCounts ? ` + ${extraCounts.settings} settings file(s)` : ''})`}
          </label>
          <label>
            <input
              type="checkbox"
              checked={includeEvents}
              onChange={(e) => setIncludeEvents(e.target.checked)}
            />{' '}
            {`Events (protection start/trip status${extraCounts ? ` + ${extraCounts.events} event file(s)` : ''})`}
          </label>
          <label>
            <input type="checkbox" checked={includeScl} onChange={(e) => setIncludeScl(e.target.checked)} />{' '}
            SCL configuration (CID/ICD){extraCounts ? ` — ${extraCounts.scl} file(s)` : ''}
          </label>
        </div>

        <input
          className={styles.desc}
          placeholder="Optional description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />

        <div className={styles.actions}>
          <button type="button" className="btn btn-primary" disabled={!canFetch || libraryMissing} onClick={() => void onFetch()}>
            {busy === 'fetch'
              ? 'Fetching from IED…'
              : selected.size > 1
                ? `Fetch ${selected.size} records & create events`
                : selected.size === 1
                  ? 'Fetch & create event'
                  : 'Fetch settings / events only'}
          </button>
          {selected.size > 1 && (
            <span className={styles.sub}>One event is created per disturbance record.</span>
          )}
        </div>
      </section>

      {warnings.length > 0 && (
        <details className={styles.warnings}>
          <summary>{warnings.length} warning(s) during fetch</summary>
          <ul>
            {warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
