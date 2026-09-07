import type { DataQuality } from '@/types';
import { explainDq } from '@/utils/statusGlossary';
import styles from './Badges.module.css';

const DQ_CLASS: Record<DataQuality, string> = {
  GOOD: styles.dqGood,
  ACCEPTABLE: styles.dqAcceptable,
  WARNING: styles.dqWarning,
  POOR: styles.dqPoor,
  INVALID: styles.dqInvalid,
};

interface Props {
  quality: DataQuality;
}

export function DataQualityBadge({ quality }: Props) {
  return (
    <span className={`${styles.badge} ${DQ_CLASS[quality]}`} title={explainDq(quality)}>
      DQ: {quality}
    </span>
  );
}
