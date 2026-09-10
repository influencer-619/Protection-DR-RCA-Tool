import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '@/services/api';
import { Skeleton } from '@/components/Skeleton';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import styles from './ChannelMappingPage.module.css';

const ROLE_COLS = ['PICKUP', 'TRIP', '52A', '52B', 'RECLOSE', 'LOCKOUT', 'UNKNOWN'] as const;

interface DigitalRow {
  name: string;
  phase?: string | null;
  inferred_role?: string;
  inferred_element?: string | null;
  assigned_role?: string;
  assigned_element?: string | null;
}

type MapEntry = { role: string; element: string };

export function DigitalTargetsPage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision } = useEventOrWorkspace(id);
  const [channels, setChannels] = useState<DigitalRow[]>([]);
  const [map, setMap] = useState<Record<string, MapEntry>>({});
  const [validRoles, setValidRoles] = useState<string[]>([]);
  const [validElements, setValidElements] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [dragCh, setDragCh] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    void api
      .getDigitalMap(id)
      .then((res) => {
        setChannels(res.channels || []);
        setValidRoles(res.valid_roles || []);
        setValidElements(res.valid_elements || []);
        const initial: Record<string, MapEntry> = {};
        for (const [k, v] of Object.entries(res.digital_map || {})) {
          initial[k] = {
            role: String(v.role || 'UNKNOWN'),
            element: String(v.element || ''),
          };
        }
        for (const ch of res.channels || []) {
          if (!initial[ch.name]) {
            initial[ch.name] = {
              role: ch.assigned_role || ch.inferred_role || 'UNKNOWN',
              element: ch.assigned_element || ch.inferred_element || '',
            };
          }
        }
        setMap(initial);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : 'Failed to load digital map'))
      .finally(() => setLoading(false));
  }, [id, analysisRevision]);

  const byRole = useMemo(() => {
    const buckets: Record<string, string[]> = {};
    for (const r of ROLE_COLS) buckets[r] = [];
    for (const ch of channels) {
      const role = map[ch.name]?.role || 'UNKNOWN';
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
      await api.putDigitalMap(id, map);
      setMsg(
        'DR targets saved. Re-run analysis so timeline / protection operate evidence use the map.',
      );
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setBusy(false);
    }
  };

  const assignRole = (chName: string, role: string) => {
    setMap((prev) => ({
      ...prev,
      [chName]: { role, element: prev[chName]?.element || '' },
    }));
  };

  const assignElement = (chName: string, element: string) => {
    setMap((prev) => ({
      ...prev,
      [chName]: { role: prev[chName]?.role || 'UNKNOWN', element },
    }));
  };

  if (loading) return <Skeleton rows={6} label="Loading DR targets" />;

  return (
    <div className="stack-md">
      <div className="page-header" style={{ padding: 0, marginBottom: 0 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>DR targets</h1>
          <p className="subtitle">
            Protection digitals → operate evidence (pickup, trip, 52a…). Roles are inferred from
            channel names; override when vendor labels are opaque — then Save and re-run analysis.
          </p>
        </div>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void save()}>
          {busy ? 'Saving…' : 'Save targets'}
        </button>
      </div>

      {msg && <div className="alert alert-info">{msg}</div>}
      {err && <div className="alert alert-danger">{err}</div>}

      {!channels.length ? (
        <div className="alert alert-info">
          No digital channels yet — upload COMTRADE with status/binary channels first.
        </div>
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
                  if (name) assignRole(name, role);
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
            <div className="panel-header">Protection digitals / operate evidence</div>
            <div className="panel-body" style={{ padding: 0 }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Channel</th>
                    <th>Inferred</th>
                    <th>DR target</th>
                    <th>Element</th>
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
                      <td className="mono">
                        {ch.inferred_role || '—'}
                        {ch.inferred_element ? ` · ${ch.inferred_element}` : ''}
                      </td>
                      <td>
                        <select
                          className="input"
                          value={map[ch.name]?.role || 'UNKNOWN'}
                          onChange={(e) => assignRole(ch.name, e.target.value)}
                        >
                          {(validRoles.length ? validRoles : ['UNKNOWN']).map((r) => (
                            <option key={r} value={r}>
                              {r}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td>
                        <select
                          className="input"
                          value={map[ch.name]?.element || ''}
                          onChange={(e) => assignElement(ch.name, e.target.value)}
                        >
                          {(validElements.length ? validElements : ['']).map((el) => (
                            <option key={el || 'none'} value={el}>
                              {el || '(auto / none)'}
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
