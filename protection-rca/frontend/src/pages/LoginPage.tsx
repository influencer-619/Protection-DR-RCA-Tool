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
    return <Navigate to="/plant" replace />;
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

      <aside className={styles.hero} aria-hidden={false}>
        <div className={styles.heroGrid} aria-hidden />
        <div className={styles.heroWave} aria-hidden />
        <div className={styles.heroInner}>
          <div className={styles.mark}>PES</div>
          <p className={styles.eyebrow}>Protection engineering workstation</p>
          <h1 className={styles.heroTitle}>Protection RCA</h1>
          <p className={styles.heroLead}>
            Disturbance-record analysis for COMTRADE oscillography, protection
            operate evidence, and root-cause review.
          </p>
          <ul className={styles.capabilities}>
            <li>IEEE C37.111 COMTRADE</li>
            <li>Pickup / trip consistency</li>
            <li>DFR event classification</li>
            <li>Scheme-aware RCA</li>
          </ul>
        </div>
        <footer className={styles.heroFoot}>
          IEC 61850 · ANSI / IEEE device functions · Engineering review
        </footer>
      </aside>

      <main className={styles.auth}>
        <div className={styles.authPanel}>
          <header className={styles.authHead}>
            <h2>Sign in</h2>
            <p>Use your plant or directory credentials to open the event workspace.</p>
          </header>

          <form onSubmit={onSubmit} className={styles.form}>
            <div className={styles.field}>
              <label htmlFor="username">Username</label>
              <input
                id="username"
                className={styles.input}
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                autoFocus
                placeholder="engineer.id"
              />
            </div>
            <div className={styles.field}>
              <label htmlFor="password">Password</label>
              <input
                id="password"
                type="password"
                className={styles.input}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
                placeholder="••••••••"
              />
            </div>
            {error && (
              <div className={styles.error} role="alert">
                {error}
              </div>
            )}
            <button type="submit" className={styles.submit} disabled={isLoading}>
              {isLoading ? 'Signing in…' : 'Sign in'}
            </button>
          </form>

          {oidcUrl && (
            <>
              <div className={styles.divider}>
                <span>or</span>
              </div>
              <a className={styles.sso} href={oidcUrl}>
                Sign in with SSO (OIDC)
              </a>
            </>
          )}

          <p className={styles.authNote}>
            Authorized protection &amp; operations personnel only. Session activity
            may be audited.
          </p>
        </div>
      </main>
    </div>
  );
}
