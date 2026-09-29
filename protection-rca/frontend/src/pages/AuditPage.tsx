import { useCallback, useEffect, useMemo, useState } from 'react';
import { format } from 'date-fns';
import { api } from '@/services/api';
import { useAuth } from '@/hooks/useAuth';
import type { AuditLogEntry } from '@/types';
import styles from './AuditPage.module.css';

const ACTION_TONE: Record<string, string> = {
  CREATE: styles.tOk,
  UPLOAD: styles.tInfo,
  ANALYSE: styles.tAccent,
  EXPORT: styles.tMuted,
  UPDATE: styles.tWarn,
  REVIEW: styles.tWarn,
  DELETE: styles.tDanger,
  CLEAR: styles.tDanger,
  LOGIN: styles.tMuted,
};

export function AuditPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<AuditLogEntry[]>([]);
  const [userNames, setUserNames] = useState<Record<string, string>>({});
  const [query, setQuery] = useState('');
  const [clearing, setClearing] = useState(false);
  const canClear = user?.role === 'ADMIN';

  const reload = useCallback(() => {
    void api.getAuditLog().then(setRows);
  }, []);

  useEffect(() => {
    reload();
    void api
      .getUsers()
      .then((list) =>
        setUserNames(Object.fromEntries(list.map((u) => [String(u.id), u.username]))),
      )
      .catch(() => undefined);
  }, [reload]);

  const userLabel = useCallback(
    (r: AuditLogEntry) => {
      if (r.username) return r.username;
      if (!r.user_id) return 'system';
      return userNames[String(r.user_id)] ?? String(r.user_id).slice(0, 8);
    },
    [userNames],
  );

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((r) =>
      [userLabel(r), r.action, r.object_type, r.object_id, r.ip_address]
        .filter(Boolean)
        .some((v) => String(v).toLowerCase().includes(q)),
    );
  }, [rows, query, userLabel]);

  const onClear = async () => {
    if (
      !window.confirm(
        'Clear the entire audit log?\n\nAll existing entries will be permanently deleted. A single CLEAR entry will be recorded for this action.',
      )
    ) {
      return;
    }
    setClearing(true);
    try {
      await api.clearAuditLog();
      reload();
    } finally {
      setClearing(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Audit log</h1>
          <p className="subtitle">Trail of user and system actions</p>
        </div>
        {canClear && (
          <button
            type="button"
            className="btn btn-danger"
            disabled={clearing || rows.length === 0}
            onClick={() => void onClear()}
          >
            {clearing ? 'Clearing…' : 'Clear audit log'}
          </button>
        )}
      </div>
      <div className={styles.toolbar}>
        <input
          type="search"
          className="form-control"
          placeholder="Filter by user, action, object or ID…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <span className={styles.count}>
          {visible.length === rows.length
            ? `${rows.length} entries`
            : `${visible.length} of ${rows.length} entries`}
        </span>
      </div>
      <div className="panel">
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>User</th>
                <th>Action</th>
                <th>Object</th>
                <th>Object ID</th>
                <th>IP</th>
              </tr>
            </thead>
            <tbody>
              {visible.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '1.5rem' }}>
                    {rows.length === 0 ? 'No audit entries' : 'No entries match the filter'}
                  </td>
                </tr>
              ) : (
                visible.map((r) => {
                  const who = userLabel(r);
                  return (
                    <tr key={r.id}>
                      <td className={`num ${styles.when}`}>{format(new Date(r.timestamp), 'yyyy-MM-dd HH:mm:ss')}</td>
                      <td>
                        <span className={styles.user} title={r.user_id ? String(r.user_id) : undefined}>
                          <span className={`${styles.avatar} ${who === 'system' ? styles.avatarSys : ''}`}>
                            {who.slice(0, 1).toUpperCase()}
                          </span>
                          {who}
                        </span>
                      </td>
                      <td>
                        <span className={`${styles.action} ${ACTION_TONE[r.action] ?? styles.tMuted}`}>
                          {r.action}
                        </span>
                      </td>
                      <td>{r.object_type ?? '—'}</td>
                      <td className={`mono ${styles.objId}`}>{r.object_id ?? '—'}</td>
                      <td className="mono">{r.ip_address ?? '—'}</td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
