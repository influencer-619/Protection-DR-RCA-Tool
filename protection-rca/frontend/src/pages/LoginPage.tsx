import { useEffect, useState, type FormEvent } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useAuthStore } from '@/stores/authStore';
import { apiClient } from '@/services/api';
import { ThemeToggle } from '@/components/ThemeToggle';
import styles from './LoginPage.module.css';

export function LoginPage() {
  const { login, isLoading, error } = useAuth();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [oidcUrl, setOidcUrl] = useState<string | null>(null);

  useEffect(() => {
    const redirect = `${window.location.origin}/login`;
    void apiClient
      .get<{ oidc_enabled: boolean; oidc_authorize_url?: string }>('/auth/mode', {
        params: { redirect_uri: redirect },
      })
      .then((r) => {
        if (r.data.oidc_enabled && r.data.oidc_authorize_url) {
          setOidcUrl(r.data.oidc_authorize_url);
        }
      })
      .catch(() => undefined);
  }, []);

  if (isAuthenticated || localStorage.getItem('protection_rca_token')) {
    return <Navigate to="/dashboard" replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      await login(username, password);
    } catch {
      /* error in store */
    }
  };

  return (
    <div className={styles.page}>
      <div className={styles.themeCorner}>
        <ThemeToggle />
      </div>
      <div className={styles.panel}>
        <div className={styles.brand}>
          <div className={styles.mark}>PES</div>
          <h1>Protection RCA</h1>
          <p>Disturbance Record / COMTRADE analysis platform</p>
        </div>
        <form onSubmit={onSubmit} className={styles.form}>
          <div className="form-group">
            <label htmlFor="username">Username</label>
            <input
              id="username"
              className="form-control"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              autoComplete="username"
              required
            />
          </div>
          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              className="form-control"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              autoComplete="current-password"
              required
            />
          </div>
          {error && (
            <div className="alert alert-error" role="alert">
              {error}
            </div>
          )}
          <button type="submit" className="btn btn-primary" style={{ width: '100%' }} disabled={isLoading}>
            {isLoading ? 'Signing in…' : 'Sign in'}
          </button>
        </form>
        {oidcUrl && (
          <a className="btn" style={{ width: '100%', marginTop: 10, textAlign: 'center' }} href={oidcUrl}>
            Sign in with SSO (OIDC)
          </a>
        )}
        <p className={styles.hint}>Engineering workstation access · JWT session · no generative AI</p>
      </div>
    </div>
  );
}
