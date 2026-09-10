import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '@/services/api';
import { Skeleton } from '@/components/Skeleton';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import { unitLabel } from '@/utils/formatElectrical';
import styles from './ChannelMappingPage.module.css';

const ROLE_OPTIONS = ['IA', 'IB', 'IC', 'IN', 'VA', 'VB', 'VC', 'VN', 'I', 'V', 'UNKNOWN'] as const;
const ROLE_COLS = ['IA', 'IB', 'IC', 'IN', 'VA', 'VB', 'VC', 'VN', 'UNKNOWN'] as const;

interface ChannelRow {
  name: string;
  phase?: string | null;
  units?: string | null;
  mapped_signal?: string | null;
  inferred?: string;
  assigned?: string;
}

export function ChannelMappingPage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision } = useEventOrWorkspace(id);
  const [channels, setChannels] = useState<ChannelRow[]>([]);
  const [map, setMap] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dragCh, setDragCh] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    void api
      .getChannelMap(id)
      .then((res) => {
        setChannels(res.channels || []);
        const initial: Record<string, string> = { ...(res.channel_map || {}) };
        for (const ch of res.channels || []) {
          if (!initial[ch.name]) {
            initial[ch.name] = ch.assigned || ch.inferred || 'UNKNOWN';
          }
        }
        setMap(initial);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : 'Failed to load channel map'))
      .finally(() => setLoading(false));
  }, [id, analysisRevision]);

  const byRole = useMemo(() => {
    const buckets: Record<string, string[]> = {};
    for (const r of ROLE_COLS) buckets[r] = [];
    for (const ch of channels) {
      const role = map[ch.name] || 'UNKNOWN';
      const key = ROLE_COLS.includes(role as (typeof ROLE_COLS)[number]) ? role : 'UNKNOWN';
      buckets[key].push(ch.name);
    }
    return buckets;
  }, [channels, map]);

  const save = async () => {
    if (!id) return;
    setBusy(true);
    setErr(null);
    setMsg(null);
    try {
      await api.putChannelMap(id, map);
      setMsg('Channel map saved. Re-run analysis to apply roles to RMS/phasors/RCA.');
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const assign = (chName: string, role: string) => {
    setMap((prev) => ({ ...prev, [chName]: role }));
  };

  const autoOk = useMemo(() => {
    if (!channels.length) return false;
    return channels.every((ch) => {
      const inferred = ch.inferred || 'UNKNOWN';
      const assigned = map[ch.name] || inferred;
      return inferred !== 'UNKNOWN' && assigned === inferred;
    });
  }, [channels, map]);

  if (loading) return <Skeleton rows={6} label="Loading channel map" />;

  return (
    <div className="stack-md">
      <div className="page-header" style={{ padding: 0, marginBottom: 0 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Channel mapping</h1>
          <p className="subtitle">
            Roles are assigned automatically from channel names / units / phase. Use this page only
            to correct mistakes — then Save and re-run analysis.
          </p>
        </div>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save mapping'}
        </button>
      </div>

      {autoOk && (
        <div className="alert alert-info" role="status">
          Auto-mapping looks complete for these channels — no change needed unless a role is wrong.
        </div>
      )}

      {msg && <div className="alert alert-info">{msg}</div>}
      {err && <div className="alert alert-danger">{err}</div>}

      {!channels.length ? (
        <div className="alert alert-info">No analog channels yet — upload COMTRADE and parse first.</div>
      ) : (
        <>
          <div className={styles.matrix}>
            {ROLE_COLS.map((role) => (
              <div
                key={role}
                className={styles.col}
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  const name = e.dataTransfer.getData('text/channel') || dragCh;
                  if (name) assign(name, role);
                  setDragCh(null);
                }}
              >
                <div className={styles.colHead}>{role}</div>
                <div className={styles.colBody}>
                  {(byRole[role] || []).map((name) => (
                    <div
                      key={name}
                      className={`mono ${styles.chip}`}
                      draggable
                      onDragStart={(e) => {
                        setDragCh(name);
                        e.dataTransfer.setData('text/channel', name);
                      }}
                    >
                      {name}
                    </div>
                  ))}
                  {!byRole[role]?.length && <div className={styles.empty}>Drop here</div>}
                </div>
              </div>
            ))}
          </div>

          <div className="panel">
            <div className="panel-header">Analog channels (table)</div>
            <div className="panel-body" style={{ padding: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>Phase</th>
                    <th>Unit</th>
                    <th>Inferred</th>
                    <th>Assigned role</th>
                  </tr>
                </thead>
                <tbody>
                  {channels.map((ch) => (
                    <tr key={ch.name}>
                      <td
                        className="mono"
                        draggable
                        onDragStart={(e) => {
                          setDragCh(ch.name);
                          e.dataTransfer.setData('text/channel', ch.name);
                        }}
                        title="Drag to matrix column"
                      >
                        {ch.name}
                      </td>
                      <td className="mono">{ch.phase ?? '—'}</td>
                      <td>{unitLabel(ch.units, ch.name)}</td>
                      <td className="mono">{ch.inferred ?? '—'}</td>
                      <td>
                        <select
                          className="input"
                          value={map[ch.name] || 'UNKNOWN'}
                          onChange={(e) => assign(ch.name, e.target.value)}
                        >
                          {ROLE_OPTIONS.map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
