import type { DataQuality } from '@/types';
import { explainDq } from '@/utils/statusGlossary';
import styles from './Badges.module.css';

const DQ_CLASS: Record<DataQuality, string> = {
  GOOD: styles.dqGood,
  // Usable tiers: show green; label still says ACCEPTABLE / WARNING
  ACCEPTABLE: styles.dqGood,
  WARNING: styles.dqGood,
  POOR: styles.dqPoor,
  INVALID: styles.dqInvalid,
};

interface Props {
  quality: DataQuality;
  label?: string;
}

export function DataQualityBadge({ quality, label }: Props) {
  const tip =
    quality === 'ACCEPTABLE' || quality === 'WARNING'
      ? `${explainDq(quality)} See COMTRADE tab for validation warnings if listed.`
      : explainDq(quality);
  return (
    <span className={`${styles.badge} ${DQ_CLASS[quality]}`} title={tip}>
      {label ?? `DQ: ${quality}`}
    </span>
  );
}
