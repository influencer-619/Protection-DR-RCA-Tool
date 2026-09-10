import { useMemo } from 'react';
import styles from './HarmonicsBars.module.css';

export interface HarmonicBarSeries {
  channel: string;
  /** order → RMS */
  harmonics: Record<string, number>;
  thdPercent?: number | null;
  color: string;
  unit?: string | null;
}

interface Props {
  title?: string;
  series: HarmonicBarSeries[];
  maxOrder?: number;
}

export function HarmonicsBars({ title = 'Harmonics', series, maxOrder = 7 }: Props) {
  const orders = useMemo(() => Array.from({ length: maxOrder }, (_, i) => String(i + 1)), [maxOrder]);

  const maxVal = useMemo(() => {
    let m = 1e-9;
    for (const s of series) {
      for (const o of orders) {
        const v = s.harmonics[o];
        if (typeof v === 'number' && v > m) m = v;
      }
    }
    return m;
  }, [series, orders]);

  if (!series.length) {
    return (
      <div className="panel">
        <div className="panel-header">{title}</div>
        <div className="panel-body" style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          Harmonic spectra appear after analysis (fault-window DFT).
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">{title}</div>
      <div className={`panel-body ${styles.body}`}>
        {series.map((s) => (
          <div key={s.channel} className={styles.row}>
            <div className={styles.head}>
              <span className={`mono ${styles.label}`} style={{ color: s.color }}>
                {s.channel}
                {s.unit ? ` (${s.unit})` : ''}
              </span>
              {s.thdPercent != null && (
                <span className={`mono ${styles.thd}`}>THD {s.thdPercent.toFixed(1)}%</span>
              )}
            </div>
            <div className={styles.chart} aria-hidden={false}>
              {orders.map((o) => {
                const v = s.harmonics[o] ?? 0;
                const h = Math.max(2, (v / maxVal) * 100);
                return (
                  <div key={o} className={styles.col}>
                    <div className={styles.barTrack}>
                      <div
                        className={styles.bar}
                        title={`H${o}: ${v.toFixed(3)}${s.unit ? ` ${s.unit}` : ''} RMS`}
                        style={{
                          height: `${h}%`,
                          background: s.color,
                          opacity: o === '1' ? 1 : 0.75,
                        }}
                      />
                    </div>
                    <div className={`mono ${styles.order}`}>{o}</div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
