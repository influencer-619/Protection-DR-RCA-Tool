import { useCallback, useEffect, useState } from 'react';
import { format } from 'date-fns';
import { api } from '@/services/api';
import { useAuth } from '@/hooks/useAuth';
import type { AuditLogEntry } from '@/types';

export function AuditPage() {
  const { user } = useAuth();
  const [rows, setRows] = useState<AuditLogEntry[]>([]);
  const [clearing, setClearing] = useState(false);
  const canClear = user?.role === 'ADMIN';

  const reload = useCallback(() => {
    void api.getAuditLog().then(setRows);
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

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
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ textAlign: 'center', padding: '1.5rem' }}>
                    No audit entries
                  </td>
                </tr>
              ) : (
                rows.map((r) => (
                  <tr key={r.id}>
                    <td className="num">{format(new Date(r.timestamp), 'yyyy-MM-dd HH:mm:ss')}</td>
                    <td className="mono">{r.username ?? r.user_id ?? '—'}</td>
                    <td className="mono">{r.action}</td>
                    <td>{r.object_type ?? '—'}</td>
                    <td className="mono" style={{ fontSize: '0.75rem' }}>
                      {r.object_id ?? '—'}
                    </td>
                    <td className="mono">{r.ip_address ?? '—'}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
