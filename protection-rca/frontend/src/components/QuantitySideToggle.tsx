import type { QuantitySideMode } from '@/utils/quantitySide';
import { sideLabel } from '@/utils/quantitySide';
import styles from './QuantitySideToggle.module.css';

interface Props {
  mode: QuantitySideMode;
  onChange: (m: QuantitySideMode) => void;
  /** Hide toggle when the record has only one side. */
  show?: boolean;
  compact?: boolean;
}

const OPTIONS: { id: QuantitySideMode; short: string }[] = [
  { id: 'secondary', short: 'Secondary' },
  { id: 'primary', short: 'Primary' },
  { id: 'both', short: 'Both' },
];

export function QuantitySideToggle({ mode, onChange, show = true, compact }: Props) {
  if (!show) return null;
  return (
    <div className={styles.wrap} title={sideLabel(mode)}>
      {!compact && <span className={styles.label}>Quantities</span>}
      <div className={styles.group} role="group" aria-label="Primary or secondary quantities">
        {OPTIONS.map((o) => (
          <button
            key={o.id}
            type="button"
            className={`${styles.btn} ${mode === o.id ? styles.active : ''}`}
            onClick={() => onChange(o.id)}
          >
            {o.short}
          </button>
        ))}
      </div>
    </div>
  );
}
