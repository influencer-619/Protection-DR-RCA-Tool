import { NavLink } from 'react-router-dom';
import styles from './EventStatusBar.module.css';

export type PipelineLamp = {
  key: string;
  label: string;
  state: 'ok' | 'warn' | 'error' | 'pending' | 'na';
  /** Event-relative tab path, e.g. "comtrade" or "waveforms" */
  to?: string;
  /** Hover detail (e.g. DQ level / warning note) */
  title?: string;
};

interface Props {
  lamps: PipelineLamp[];
  /** Base path `/events/:id` — when set, lamps with `to` become clickable tabs */
  eventBase?: string;
}

const ICON: Record<PipelineLamp['state'], string> = {
  ok: '✓',
  warn: '⚠',
  error: '●',
  pending: '○',
  na: '—',
};

export function EventStatusBar({ lamps, eventBase }: Props) {
  return (
    <div className={styles.bar} role="navigation" aria-label="Event analysis stages">
      {lamps.map((l) => {
        const className = `${styles.item} ${styles[l.state]}`;
        if (eventBase && l.to) {
          return (
            <NavLink
              key={l.key}
              to={`${eventBase}/${l.to}`}
              className={({ isActive }) =>
                `${className} ${styles.link} ${isActive ? styles.linkActive : ''}`
              }
              title={l.title || `Open ${l.label}`}
            >
              <span className={styles.icon}>{ICON[l.state]}</span>
              <span className={styles.label}>{l.label}</span>
            </NavLink>
          );
        }
        return (
          <div key={l.key} className={className} title={l.title}>
            <span className={styles.icon}>{ICON[l.state]}</span>
            <span className={styles.label}>{l.label}</span>
          </div>
        );
      })}
    </div>
  );
}
