import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useEffect } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { ThemeToggle } from '@/components/ThemeToggle';
import styles from './AppLayout.module.css';

/** Sidebar focused on disturbance-record analysis + RCA (no plant/settings registry). */
const NAV: Array<
  | { to: string; label: string }
  | { label: string; children: Array<{ to: string; label: string }> }
> = [
  {
    label: 'Analysis',
    children: [
      { to: '/dashboard', label: 'Dashboard' },
      { to: '/events', label: 'Events' },
      { to: '/events/new', label: 'Create event' },
      { to: '/upload', label: 'Upload files' },
    ],
  },
  {
    label: 'Administration',
    children: [
      { to: '/users', label: 'Users' },
      { to: '/audit', label: 'Audit' },
    ],
  },
  { to: '/help', label: 'Help' },
];

export function AppLayout() {
  const { user, logout } = useAuth();
  const location = useLocation();

  // Keep EventLayout mounted across event tabs; remount other pages on path change.
  const outletKey = (() => {
    const m = location.pathname.match(/^(\/events\/[^/]+)/);
    if (m) return m[1];
    return `${location.pathname}${location.search}`;
  })();

  useEffect(() => {
    const main = document.querySelector('main');
    if (main) main.scrollTop = 0;
  }, [location.pathname, location.search]);

  return (
    <div className={styles.shell}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <div className={styles.brandMark}>PES</div>
          <div>
            <div className={styles.brandName}>Protection RCA</div>
            <div className={styles.brandSub}>Disturbance Analysis</div>
          </div>
        </div>
        <nav className={styles.nav}>
          {NAV.map((item) =>
            'children' in item && item.children ? (
              <div key={item.label} className={styles.group}>
                <div className={styles.groupLabel}>{item.label}</div>
                {item.children.map((c) => (
                  <NavLink
                    key={c.to}
                    to={c.to}
                    className={({ isActive }) =>
                      `${styles.link} ${styles.sub} ${isActive ? styles.active : ''}`
                    }
                    end
                  >
                    {c.label}
                  </NavLink>
                ))}
              </div>
            ) : (
              <NavLink
                key={'to' in item ? item.to : item.label}
                to={'to' in item ? item.to : '/'}
                className={({ isActive }) => `${styles.link} ${isActive ? styles.active : ''}`}
              >
                {item.label}
              </NavLink>
            ),
          )}
        </nav>
      </aside>
      <div className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.topTitle}>Protection Disturbance Record / COMTRADE RCA</div>
          <div className={styles.userBlock}>
            <ThemeToggle />
            <div className={styles.userMeta}>
              <span className={styles.userName}>{user?.full_name || user?.username || '—'}</span>
              <span className={`mono ${styles.userRole}`}>{user?.role ?? '—'}</span>
            </div>
            <button type="button" className="btn btn-sm" onClick={logout}>
              Sign out
            </button>
          </div>
        </header>
        <main className={styles.content}>
          <Outlet key={outletKey} />
        </main>
      </div>
    </div>
  );
}
