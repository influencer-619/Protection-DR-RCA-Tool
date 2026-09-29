import { NavLink, Outlet, useLocation } from 'react-router-dom';
import { useEffect, useState, type ReactNode } from 'react';
import { useAuth } from '@/hooks/useAuth';
import { ThemeToggle } from '@/components/ThemeToggle';
import styles from './AppLayout.module.css';

type IconName = 'plant' | 'dashboard' | 'events' | 'users' | 'audit' | 'help';

const ICON_PATHS: Record<IconName, ReactNode> = {
  plant: (
    <>
      <path d="M3 21h18" />
      <path d="M5 21V10l7-5 7 5v11" />
      <path d="M12 9l-2 4h4l-2 4" />
    </>
  ),
  dashboard: (
    <>
      <rect x="3" y="3" width="7" height="9" rx="1" />
      <rect x="14" y="3" width="7" height="5" rx="1" />
      <rect x="14" y="12" width="7" height="9" rx="1" />
      <rect x="3" y="16" width="7" height="5" rx="1" />
    </>
  ),
  events: <path d="M3 12h4l2-6 4 12 2-6h6" />,
  users: (
    <>
      <circle cx="9" cy="8" r="3.5" />
      <path d="M2.5 20c.8-3.6 3.4-5.5 6.5-5.5s5.7 1.9 6.5 5.5" />
      <path d="M16 4.5a3.5 3.5 0 010 7M18.5 14.8c1.6.8 2.6 2.5 3 5.2" />
    </>
  ),
  audit: (
    <>
      <path d="M12 3l8 3v6c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V6l8-3z" />
      <path d="M8.5 12l2.5 2.5 4.5-5" />
    </>
  ),
  help: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9.5 9.5a2.5 2.5 0 114 2c-1 .7-1.5 1.2-1.5 2.5" />
      <path d="M12 17h.01" />
    </>
  ),
};

function Icon({ name }: { name: IconName }) {
  return (
    <svg
      className={styles.icon}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {ICON_PATHS[name]}
    </svg>
  );
}

type NavItem = { to: string; label: string; icon: IconName; end?: boolean };

/** Sidebar: plant-first analysis (upload only under IED). */
const NAV: Array<{ label?: string; items: NavItem[] }> = [
  { items: [{ to: '/plant', label: 'Plant', icon: 'plant' }] },
  {
    label: 'Analysis',
    items: [
      { to: '/dashboard', label: 'Dashboard', icon: 'dashboard', end: true },
      { to: '/events', label: 'All events', icon: 'events', end: true },
    ],
  },
  {
    label: 'Administration',
    items: [
      { to: '/users', label: 'Users', icon: 'users', end: true },
      { to: '/audit', label: 'Audit', icon: 'audit', end: true },
    ],
  },
];

const COLLAPSE_KEY = 'pes.sidebarCollapsed';

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase();
}

const PAGE_TITLES: Array<[RegExp, string]> = [
  [/^\/plant\/ieds\//, 'IED workspace'],
  [/^\/plant/, 'Plant hierarchy'],
  [/^\/dashboard/, 'Dashboard'],
  [/^\/events\/compare/, 'Compare events'],
  [/^\/events\/[^/]+/, 'Event analysis'],
  [/^\/events/, 'All events'],
  [/^\/users/, 'Users'],
  [/^\/audit/, 'Audit trail'],
  [/^\/help/, 'Help & guide'],
];

function pageTitle(path: string): string {
  return PAGE_TITLES.find(([re]) => re.test(path))?.[1] ?? 'Protection RCA';
}

export function AppLayout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem(COLLAPSE_KEY) === '1');

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

  useEffect(() => {
    localStorage.setItem(COLLAPSE_KEY, collapsed ? '1' : '0');
  }, [collapsed]);

  const displayName = user?.full_name || user?.username || '—';
  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `${styles.link} ${isActive ? styles.active : ''}`;

  return (
    <div className={`${styles.shell} ${collapsed ? styles.collapsed : ''}`}>
      <aside className={styles.sidebar}>
        <div className={styles.brand}>
          <div className={styles.brandMark}>
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d="M13 2L4 14h6l-1 8 9-12h-6l1-8z" />
            </svg>
          </div>
          <div className={styles.brandText}>
            <div className={styles.brandName}>Protection RCA</div>
            <div className={styles.brandSub}>Disturbance Analysis</div>
          </div>
        </div>

        <nav className={styles.nav}>
          {NAV.map((group, gi) => (
            <div key={group.label ?? gi} className={styles.group}>
              {group.label && <div className={styles.groupLabel}>{group.label}</div>}
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  className={linkClass}
                  title={collapsed ? item.label : undefined}
                >
                  <Icon name={item.icon} />
                  <span className={styles.linkLabel}>{item.label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className={styles.footer}>
          <NavLink to="/help" className={linkClass} title={collapsed ? 'Help' : undefined}>
            <Icon name="help" />
            <span className={styles.linkLabel}>Help &amp; guide</span>
          </NavLink>
          <button
            type="button"
            className={styles.collapseBtn}
            onClick={() => setCollapsed((c) => !c)}
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path d={collapsed ? 'M9 6l6 6-6 6' : 'M15 6l-6 6 6 6'} />
            </svg>
          </button>
        </div>
      </aside>
      <div className={styles.main}>
        <header className={styles.topbar}>
          <div className={styles.crumbs}>
            <span className={styles.crumbRoot}>Protection RCA</span>
            <svg className={styles.crumbSep} viewBox="0 0 24 24" aria-hidden="true">
              <path d="M9 6l6 6-6 6" />
            </svg>
            <span className={styles.crumbPage}>{pageTitle(location.pathname)}</span>
          </div>
          <div className={styles.userBlock}>
            <span className={styles.envChip} title="Disturbance record / COMTRADE analysis">
              <span className={styles.envDot} />
              COMTRADE RCA
            </span>
            <ThemeToggle className={styles.iconBtn} iconOnly />
            <div className={styles.userChip}>
              <div className={styles.avatarSm}>{initials(displayName)}</div>
              <div className={styles.userMeta}>
                <span className={styles.userName}>{displayName}</span>
                <span className={styles.userRole}>{user?.role ?? '—'}</span>
              </div>
            </div>
            <button
              type="button"
              className={styles.iconBtn}
              onClick={logout}
              title="Sign out"
              aria-label="Sign out"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="M15 4h3a2 2 0 012 2v12a2 2 0 01-2 2h-3" />
                <path d="M10 17l-5-5 5-5M5 12h11" />
              </svg>
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
