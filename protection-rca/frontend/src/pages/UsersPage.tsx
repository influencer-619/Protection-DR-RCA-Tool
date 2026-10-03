import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { api } from '@/services/api';
import { useAuth } from '@/hooks/useAuth';
import type { User, UserRole } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import styles from './UsersPage.module.css';

const ROLES: { value: UserRole; label: string }[] = [
  { value: 'VIEWER', label: 'Viewer' },
  { value: 'ANALYST', label: 'Analyst' },
  { value: 'PROTECTION_ENGINEER', label: 'Protection engineer' },
  { value: 'APPROVER', label: 'Approver' },
  { value: 'ADMIN', label: 'Administrator' },
];

type FormState = {
  username: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  password: string;
  confirm: string;
};

const emptyForm = (): FormState => ({
  username: '',
  email: '',
  full_name: '',
  role: 'ANALYST',
  is_active: true,
  password: '',
  confirm: '',
});

function apiDetail(err: unknown): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((d) => (typeof d === 'object' && d && 'msg' in d ? String((d as { msg: unknown }).msg) : String(d)))
      .join('; ');
  }
  if (err instanceof Error && err.message) return err.message;
  return 'Request failed';
}

export function UsersPage() {
  const { user: me } = useAuth();
  const [rows, setRows] = useState<User[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'create' | 'edit' | null>(null);
  const [editing, setEditing] = useState<User | null>(null);
  const [form, setForm] = useState<FormState>(emptyForm);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      setRows(await api.getUsers());
      setError(null);
    } catch (err) {
      setError(apiDetail(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setError(null);
    setMode('create');
  };

  const openEdit = (u: User) => {
    setEditing(u);
    setForm({
      username: u.username,
      email: u.email,
      full_name: u.full_name ?? '',
      role: u.role,
      is_active: u.is_active,
      password: '',
      confirm: '',
    });
    setError(null);
    setMode('edit');
  };

  const closeModal = () => {
    if (busy) return;
    setMode(null);
    setEditing(null);
    setForm(emptyForm());
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!form.username.trim() || !form.email.trim()) {
      setError('Username and email are required.');
      return;
    }
    if (mode === 'create' && form.password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (form.password && form.password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (form.password !== form.confirm) {
      setError('Password confirmation does not match.');
      return;
    }

    setBusy(true);
    try {
      if (mode === 'create') {
        await api.createUser({
          username: form.username.trim(),
          email: form.email.trim(),
          full_name: form.full_name.trim() || null,
          role: form.role,
          is_active: form.is_active,
          password: form.password,
        });
      } else if (mode === 'edit' && editing) {
        const body: Parameters<typeof api.updateUser>[1] = {
          username: form.username.trim(),
          email: form.email.trim(),
          full_name: form.full_name.trim() || null,
          role: form.role,
          is_active: form.is_active,
        };
        if (form.password) body.password = form.password;
        await api.updateUser(editing.id, body);
      }
      setMode(null);
      setEditing(null);
      await reload();
    } catch (err) {
      setError(apiDetail(err));
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (u: User) => {
    if (me?.id === u.id) {
      setError('You cannot delete your own account.');
      return;
    }
    if (
      !window.confirm(
        `Delete user “${u.username}”?\n\nThis permanently removes the account. This cannot be undone.`,
      )
    ) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.deleteUser(u.id);
      await reload();
    } catch (err) {
      setError(apiDetail(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page">
      <div className="page-header">
        <div>
          <h1>Users</h1>
          <p className="subtitle">Create, edit, and deactivate platform accounts</p>
        </div>
        <button type="button" className="btn btn-primary" onClick={openCreate} disabled={busy}>
          Add user
        </button>
      </div>

      {error && !mode && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

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
                <th>Last login</th>
                <th className={styles.actionsCol}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && (
                <tr>
                  <td colSpan={7} className={styles.empty}>
                    Loading users…
                  </td>
                </tr>
              )}
              {!loading && rows.length === 0 && (
                <tr>
                  <td colSpan={7} className={styles.empty}>
                    No users found.
                  </td>
                </tr>
              )}
              {!loading &&
                rows.map((r) => (
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
                    <td className="mono">
                      {r.last_login_at
                        ? new Date(r.last_login_at).toLocaleString()
                        : '—'}
                    </td>
                    <td>
                      <div className={styles.actions}>
                        <button
                          type="button"
                          className="btn btn-sm"
                          onClick={() => openEdit(r)}
                          disabled={busy}
                        >
                          Edit
                        </button>
                        <button
                          type="button"
                          className="btn btn-sm btn-danger"
                          onClick={() => void onDelete(r)}
                          disabled={busy || me?.id === r.id}
                          title={me?.id === r.id ? 'Cannot delete your own account' : 'Delete user'}
                        >
                          Delete
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>
      </div>

      {mode && (
        <div className="modal-backdrop" role="presentation" onClick={closeModal}>
          <div
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="user-modal-title"
            onClick={(ev) => ev.stopPropagation()}
          >
            <div className="modal-header">
              <h2 id="user-modal-title">{mode === 'create' ? 'Add user' : 'Edit user'}</h2>
              <button type="button" className="btn btn-ghost btn-sm" onClick={closeModal} disabled={busy}>
                Close
              </button>
            </div>
            <form onSubmit={(e) => void onSubmit(e)}>
              <div className="modal-body">
                {error && (
                  <div className="alert alert-error" role="alert" style={{ marginBottom: 12 }}>
                    {error}
                  </div>
                )}
                <div className={styles.formGrid}>
                  <label>
                    <span className="form-label">Username</span>
                    <input
                      className="form-control"
                      value={form.username}
                      onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
                      autoComplete="off"
                      required
                    />
                  </label>
                  <label>
                    <span className="form-label">Full name</span>
                    <input
                      className="form-control"
                      value={form.full_name}
                      onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
                      autoComplete="name"
                    />
                  </label>
                  <label className={styles.span2}>
                    <span className="form-label">Email</span>
                    <input
                      className="form-control"
                      type="email"
                      value={form.email}
                      onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                      autoComplete="email"
                      required
                    />
                  </label>
                  <label>
                    <span className="form-label">Role</span>
                    <select
                      className="form-control"
                      value={form.role}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, role: e.target.value as UserRole }))
                      }
                    >
                      {ROLES.map((r) => (
                        <option key={r.value} value={r.value}>
                          {r.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className={styles.checkLabel}>
                    <span className="form-label">Account status</span>
                    <span className={styles.checkRow}>
                      <input
                        type="checkbox"
                        checked={form.is_active}
                        onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
                      />
                      Active (can sign in)
                    </span>
                  </label>
                  <label>
                    <span className="form-label">
                      {mode === 'create' ? 'Password' : 'New password (optional)'}
                    </span>
                    <input
                      className="form-control"
                      type="password"
                      value={form.password}
                      onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
                      autoComplete="new-password"
                      required={mode === 'create'}
                      minLength={mode === 'create' || form.password ? 8 : undefined}
                      placeholder={mode === 'edit' ? 'Leave blank to keep current' : undefined}
                    />
                  </label>
                  <label>
                    <span className="form-label">Confirm password</span>
                    <input
                      className="form-control"
                      type="password"
                      value={form.confirm}
                      onChange={(e) => setForm((f) => ({ ...f, confirm: e.target.value }))}
                      autoComplete="new-password"
                      required={mode === 'create' || Boolean(form.password)}
                    />
                  </label>
                </div>
                <p className={styles.hint}>
                  Roles: Viewer (read) · Analyst (run analysis) · Protection engineer · Approver ·
                  Admin (user management). Password minimum 8 characters.
                </p>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-ghost" onClick={closeModal} disabled={busy}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary" disabled={busy}>
                  {busy ? 'Saving…' : mode === 'create' ? 'Create user' : 'Save changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
