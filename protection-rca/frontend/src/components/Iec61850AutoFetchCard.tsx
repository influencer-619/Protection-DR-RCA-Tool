import { useCallback, useEffect, useRef, useState } from 'react';
import { formatDistanceToNow } from 'date-fns';
import { api } from '@/services/api';
import type { Iec61850AutoFetch, Iec61850AutoFetchSettings, Iec61850ConnectionInput } from '@/types';
import styles from './Iec61850FetchPanel.module.css';

interface Props {
  iedId: string;
  connection: () => Iec61850ConnectionInput;
  disabled: boolean;
  onNewEvents: () => void;
}

const POLL_MS = 20000;

function ago(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : formatDistanceToNow(d, { addSuffix: true });
}

function intervalLabel(min: number): string {
  return min < 60 ? `${min} min` : `${min / 60} h`;
}

export function Iec61850AutoFetchCard({ iedId, connection, disabled, onNewEvents }: Props) {
  const [state, setState] = useState<Iec61850AutoFetch | null>(null);
  const [busy, setBusy] = useState<null | 'save' | 'run'>(null);
  const [error, setError] = useState<string | null>(null);
  const lastTotal = useRef<number | null>(null);

  const apply = useCallback(
    (next: Iec61850AutoFetch) => {
      setState(next);
      if (lastTotal.current != null && next.total_events_created > lastTotal.current) onNewEvents();
      lastTotal.current = next.total_events_created;
    },
    [onNewEvents],
  );

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      api
        .getIec61850AutoFetch(iedId)
        .then((s) => !cancelled && apply(s))
        .catch(() => undefined);
    void load();
    const t = window.setInterval(load, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(t);
    };
  }, [iedId, apply]);

  const save = async (patch: Partial<Iec61850AutoFetchSettings>) => {
    if (!state) return;
    setBusy('save');
    setError(null);
    const conn = connection();
    try {
      apply(
        await api.saveIec61850AutoFetch(iedId, {
          enabled: state.enabled,
          interval_min: state.interval_min,
          include_settings: state.include_settings,
          include_events: state.include_events,
          auto_analyse: state.auto_analyse,
          import_existing: state.import_existing,
          ...(conn.host ? conn : {}),
          ...patch,
          also_fetch_remote: false,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not save auto-fetch settings');
    } finally {
      setBusy(null);
    }
  };

  const runNow = async () => {
    setBusy('run');
    setError(null);
    try {
      apply(await api.runIec61850AutoFetchNow(iedId));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Auto-fetch check failed');
    } finally {
      setBusy(null);
    }
  };

  if (!state) return null;
  const locked = disabled || !!busy;

  return (
    <div className={`${styles.autoCard} ${state.enabled ? styles.autoOn : ''}`}>
      <div className={styles.autoHead}>
        <label className={styles.switch}>
          <input
            type="checkbox"
            role="switch"
            checked={state.enabled}
            disabled={locked}
            onChange={(e) => void save({ enabled: e.target.checked })}
          />
          <strong>Auto-fetch new records</strong>
        </label>
        <label className={styles.inline}>
          every
          <select
            value={state.interval_min}
            disabled={locked}
            onChange={(e) => void save({ interval_min: Number(e.target.value) })}
          >
            {state.interval_choices.map((m) => (
              <option key={m} value={m}>
                {intervalLabel(m)}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="btn btn-sm"
          disabled={locked || !state.enabled}
          onClick={() => void runNow()}
        >
          {busy === 'run' ? 'Checking…' : 'Check now'}
        </button>
      </div>

      <p className={styles.sub}>
        When on, the server checks <strong>this IED</strong> on schedule and, for every new
        disturbance record, creates an event with the record
        {state.include_settings ? ', settings' : ''}
        {state.include_events ? ', events' : ''}
        {state.auto_analyse ? ' and starts analysis' : ''}. Works without this page open.
      </p>

      <div className={styles.autoOptions}>
        <label>
          <input
            type="checkbox"
            checked={state.include_settings}
            disabled={locked}
            onChange={(e) => void save({ include_settings: e.target.checked })}
          />{' '}
          Settings
        </label>
        <label>
          <input
            type="checkbox"
            checked={state.include_events}
            disabled={locked}
            onChange={(e) => void save({ include_events: e.target.checked })}
          />{' '}
          Events
        </label>
        <label>
          <input
            type="checkbox"
            checked={state.auto_analyse}
            disabled={locked}
            onChange={(e) => void save({ auto_analyse: e.target.checked })}
          />{' '}
          Start analysis automatically (normal / this IED)
        </label>
        <label title="Applies when auto-fetch is switched on">
          <input
            type="checkbox"
            checked={state.import_existing}
            disabled={locked || state.enabled}
            onChange={(e) => void save({ import_existing: e.target.checked })}
          />{' '}
          Also import records already on the IED
        </label>
      </div>

      {state.enabled && (
        <div className={styles.autoStatus}>
          {!state.scheduler_running && (
            <div className={styles.warn}>
              Background scheduler is not running on the server (IEC61850_AUTO_FETCH disabled or
              client library missing). Use “Check now” meanwhile.
            </div>
          )}
          <span>
            Last check: <strong>{ago(state.last_run_at)}</strong>
            {state.last_status === 'OK' && (
              <>
                {' '}
                · {state.last_new_records ?? 0} new
                {state.records_on_ied != null && <> · {state.records_on_ied} record(s) on IED</>}
              </>
            )}
          </span>
          <span>
            Next check: <strong>{state.next_run_at ? ago(state.next_run_at) : 'within 30 s'}</strong>
          </span>
          <span>
            Events created by auto-fetch: <strong>{state.total_events_created}</strong>
            {state.last_event_at && <> (latest {ago(state.last_event_at)})</>}
          </span>
          {!state.baseline_done && !state.import_existing && (
            <span className={styles.sub}>
              First check records what is already on the IED; only records that appear after that
              are imported.
            </span>
          )}
          {state.last_status === 'ERROR' && state.last_error && (
            <div className={styles.error}>Last check failed: {state.last_error}</div>
          )}
        </div>
      )}

      {error && <div className={styles.error}>{error}</div>}
    </div>
  );
}
