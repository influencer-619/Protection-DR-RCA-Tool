import { Link } from 'react-router-dom';
import { StatusBadge } from '@/components/StatusBadge';
import styles from './VerdictStrip.module.css';

export interface VerdictStripProps {
  faultType?: string | null;
  tripSummary?: string | null;
  consistency?: string | null;
  inconsistentCount?: number;
  rcaTitle?: string | null;
  rcaCode?: string | null;
  eventStatus?: string | null;
  decisionState?: string | null;
  nextLabel?: string;
  nextTo?: string;
  nextOnClick?: () => void;
  compact?: boolean;
}

/** Level-1 HMI overview: one glance at what happened + where to go next. */
export function VerdictStrip({
  faultType,
  tripSummary,
  consistency,
  inconsistentCount = 0,
  rcaTitle,
  rcaCode,
  eventStatus,
  decisionState,
  nextLabel,
  nextTo,
  nextOnClick,
  compact = false,
}: VerdictStripProps) {
  const cons = (consistency || '').toUpperCase();
  const consTone =
    cons === 'INCONSISTENT' ? styles.bad : cons === 'CONSISTENT' ? styles.ok : styles.muted;
  const statusUp = (eventStatus || '').toUpperCase();
  const loudFail = statusUp === 'FAILED';

  return (
    <div
      className={`${styles.strip} ${loudFail ? styles.fail : ''} ${compact ? styles.compact : ''}`}
      role="status"
    >
      <div className={styles.parts}>
        {eventStatus && (
          <span className={styles.part}>
            <StatusBadge status={eventStatus} />
          </span>
        )}
        {decisionState && decisionState !== eventStatus && (
          <span className={styles.part}>
            <StatusBadge status={decisionState} />
          </span>
        )}
        <span className={styles.part}>
          <span className={styles.k}>Fault</span>
          <span className={`mono ${styles.v}`}>{faultType || 'UNKNOWN'}</span>
        </span>
        <span className={styles.sep} aria-hidden>
          ·
        </span>
        <span className={styles.part}>
          <span className={styles.k}>Trip</span>
          <span className={styles.v}>{tripSummary || 'None asserted'}</span>
        </span>
        <span className={styles.sep} aria-hidden>
          ·
        </span>
        <span className={styles.part}>
          <span className={styles.k}>Consistency</span>
          <span className={`${styles.v} ${consTone}`}>
            {consistency || '—'}
            {inconsistentCount > 0 ? ` (${inconsistentCount})` : ''}
          </span>
        </span>
        <span className={styles.sep} aria-hidden>
          ·
        </span>
        <span className={styles.part}>
          <span className={styles.k}>RCA</span>
          <span className={styles.v}>
            {rcaCode ? <span className="mono">{rcaCode} </span> : null}
            {rcaTitle || 'Not available'}
          </span>
        </span>
      </div>
      {(nextTo || nextOnClick) && (
        <div className={styles.next}>
          {nextOnClick ? (
            <button type="button" className="btn btn-sm btn-primary" onClick={nextOnClick}>
              {nextLabel || 'Continue'}
            </button>
          ) : nextTo ? (
            <Link to={nextTo} className="btn btn-sm btn-primary">
              {nextLabel || 'Continue'}
            </Link>
          ) : null}
        </div>
      )}
    </div>
  );
}
