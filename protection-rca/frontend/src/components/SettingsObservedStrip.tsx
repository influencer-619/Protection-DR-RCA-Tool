import styles from './SettingsObservedStrip.module.css';

export interface ObservedTiming {
  pickup_s?: number | null;
  trip_s?: number | null;
  breaker_s?: number | null;
  interrupt_s?: number | null;
}

export interface ExpectedTiming {
  pickup_s?: number | null;
  trip_s?: number | null;
  bf_timer_s?: number | null;
  source?: string | null;
}

interface Props {
  expected?: ExpectedTiming | null;
  observed?: ObservedTiming | null;
}

function fmt(v?: number | null): string {
  if (v == null || Number.isNaN(v)) return '—';
  return `${(v * 1000).toFixed(0)} ms`;
}

function delta(exp?: number | null, obs?: number | null): string {
  if (exp == null || obs == null) return '';
  const d = (obs - exp) * 1000;
  const sign = d >= 0 ? '+' : '';
  return `${sign}${d.toFixed(0)} ms`;
}

export function SettingsObservedStrip({ expected, observed }: Props) {
  const rows = [
    { key: 'Pickup', exp: expected?.pickup_s, obs: observed?.pickup_s },
    { key: 'Trip', exp: expected?.trip_s, obs: observed?.trip_s },
    { key: 'Breaker', exp: null, obs: observed?.breaker_s },
    { key: 'Interrupt', exp: expected?.bf_timer_s, obs: observed?.interrupt_s, expLabel: 'BF timer' },
  ];

  return (
    <div className={`panel ${styles.wrap}`}>
      <div className="panel-header">Settings vs observed timing</div>
      <div className={`panel-body ${styles.body}`}>
        <div className={styles.grid}>
          <div className={styles.row}>
            <div className={styles.head}>Stage</div>
            <div className={styles.head}>Expected (settings)</div>
            <div className={styles.head}>Observed (record)</div>
            <div className={styles.head}>Δ</div>
          </div>
          {rows.map((r) => (
            <div key={r.key} className={styles.row}>
              <div className={styles.cell}>{r.expLabel || r.key}</div>
              <div className={`mono ${styles.cell}`}>{fmt(r.exp)}</div>
              <div className={`mono ${styles.cell}`}>{fmt(r.obs)}</div>
              <div className={`mono ${styles.delta}`}>{delta(r.exp, r.obs) || '—'}</div>
            </div>
          ))}
        </div>
        <p className={styles.hint}>
          Expected times come from settings when present; observed from timeline. Missing values
          stay blank — never invented.
          {expected?.source ? ` Source: ${expected.source}.` : ''}
        </p>
      </div>
    </div>
  );
}
