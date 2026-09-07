import type { ConsistencyStatus, EventStatus } from '@/types';
import { explainStatus } from '@/utils/statusGlossary';
import styles from './Badges.module.css';

const STATUS_CLASS: Record<string, string> = {
  UPLOADED: styles.pending,
  PARSING: styles.pending,
  ANALYZING: styles.running,
  AWAITING_REVIEW: styles.warn,
  REVIEW: styles.warn,
  CLOSED: styles.ok,
  FAILED: styles.error,
  CONSISTENT: styles.ok,
  INCONSISTENT: styles.error,
  UNVERIFIABLE: styles.warn,
  DATA_QUALITY_ISSUE: styles.warn,
  CONSISTENT_WITH_WARNINGS: styles.warn,
  VALID: styles.ok,
  VALID_WITH_WARNINGS: styles.warn,
  INVALID: styles.error,
  NOT_VALIDATED: styles.neutral,
  PARTIALLY_SUPPORTED: styles.warn,
  SUPPORTED: styles.ok,
  PENDING: styles.pending,
  RUNNING: styles.running,
  COMPLETED: styles.ok,
  CANCELLED: styles.neutral,
  STORED: styles.ok,
  VALIDATED: styles.ok,
  DRAFT: styles.neutral,
  APPROVED: styles.ok,
  REJECTED: styles.error,
  SUPERSEDED: styles.neutral,
  PROBABLE: styles.warn,
  CONFIRMED: styles.ok,
  POSSIBLE: styles.pending,
  UNLIKELY: styles.neutral,
  INCONCLUSIVE: styles.warn,
  CLASSIFIED: styles.ok,
  UNKNOWN: styles.neutral,
  ANALYSIS_COMPLETE: styles.ok,
  ANALYSIS_COMPLETE_WITH_WARNINGS: styles.warn,
  ENGINEER_REVIEW_REQUIRED: styles.warn,
  DATA_INSUFFICIENT: styles.error,
  UNSUPPORTED_FORMAT: styles.error,
};

interface Props {
  status: EventStatus | ConsistencyStatus | string;
  label?: string;
}

export function StatusBadge({ status, label }: Props) {
  const cls = STATUS_CLASS[status] ?? styles.neutral;
  return (
    <span className={`${styles.badge} ${cls}`} title={explainStatus(status)}>
      {label ?? status.replace(/_/g, ' ')}
    </span>
  );
}
