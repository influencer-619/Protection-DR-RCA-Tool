import type { Severity } from '@/types';
import styles from './Badges.module.css';

const SEV_CLASS: Record<Severity, string> = {
  INFO: styles.sevInfo,
  LOW: styles.sevLow,
  MEDIUM: styles.sevMedium,
  HIGH: styles.sevHigh,
  CRITICAL: styles.sevCritical,
};

interface Props {
  severity: Severity;
}

export function SeverityBadge({ severity }: Props) {
  return (
    <span className={`${styles.badge} ${SEV_CLASS[severity]}`}>
      {severity}
    </span>
  );
}
