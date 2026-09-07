import { useEffect, useState } from 'react';
import { api } from '@/services/api';
import type { User } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';

export function UsersPage() {
  const [rows, setRows] = useState<User[]>([]);
  useEffect(() => {
    void api.getUsers().then(setRows);
  }, []);

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Users</h1>
          <p className="subtitle">Platform accounts and roles</p>
        </div>
      </div>
      <div className="panel">
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Username</th>
                <th>Name</th>
                <th>Email</th>
                <th>Role</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono">{r.username}</td>
                  <td>{r.full_name ?? '—'}</td>
                  <td>{r.email}</td>
                  <td className="mono">{r.role}</td>
                  <td>
                    <StatusBadge
                      status={r.is_active ? 'COMPLETED' : 'CANCELLED'}
                      label={r.is_active ? 'ACTIVE' : 'INACTIVE'}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
