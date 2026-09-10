import { useMemo, useState } from 'react';
import styles from './HarmonicsHeatmap.module.css';

export interface HarmonicsHeatmapChannel {
  channel: string;
  times_s: number[];
  harmonics_rms: Record<string, number[]>;
  unit?: string | null;
  color?: string;
}

interface Props {
  title?: string;
  channels: HarmonicsHeatmapChannel[];
  maxOrder?: number;
}

function heatColor(t: number): string {
  // t in [0,1]: dark → amber → white (readable on dark panels)
  const u = Math.max(0, Math.min(1, t));
  const r = Math.round(20 + u * 220);
  const g = Math.round(24 + u * 140);
  const b = Math.round(32 + (1 - u) * 40);
  return `rgb(${r},${g},${b})`;
}

export function HarmonicsHeatmap({
  title = 'Harmonics heatmap (time × order)',
  channels,
  maxOrder = 7,
}: Props) {
  const [active, setActive] = useState(0);
  const orders = useMemo(
    () => Array.from({ length: maxOrder }, (_, i) => String(i + 1)),
    [maxOrder],
  );

  const ch = channels[Math.min(active, Math.max(0, channels.length - 1))];

  const { grid, maxVal, times } = useMemo(() => {
    if (!ch) return { grid: [] as number[][], maxVal: 1, times: [] as number[] };
    const times = ch.times_s || [];
    let maxVal = 1e-12;
    const grid = orders.map((o) => {
      const row = ch.harmonics_rms[o] || [];
      return times.map((_, ti) => {
        const v = row[ti] ?? 0;
        if (v > maxVal) maxVal = v;
        return v;
      });
    });
    return { grid, maxVal, times };
  }, [ch, orders]);

  if (!channels.length || !ch || !times.length) {
    return (
      <div className="panel">
        <div className="panel-header">{title}</div>
        <div className="panel-body" style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          Time–harmonic heatmaps appear after analysis (short-time DFT on fault-window currents).
        </div>
      </div>
    );
  }

  return (
    <div className="panel">
      <div className="panel-header">{title}</div>
      <div className={`panel-body ${styles.body}`}>
        {channels.length > 1 && (
          <div className={styles.tabs}>
            {channels.map((c, i) => (
              <button
                key={c.channel}
                type="button"
                className={i === active ? styles.tabActive : styles.tab}
                onClick={() => setActive(i)}
              >
                {c.channel}
              </button>
            ))}
          </div>
        )}
        <div className={styles.meta}>
          <span className="mono">
            {ch.channel}
            {ch.unit ? ` (${ch.unit})` : ''}
          </span>
          <span className="mono" style={{ color: 'var(--text-muted)' }}>
            {times.length} frames · H1–H{maxOrder}
          </span>
        </div>
        <div className={styles.gridWrap}>
          <div className={styles.yLabels}>
            {orders.map((o) => (
              <div key={o} className={`mono ${styles.yLab}`}>
                H{o}
              </div>
            ))}
          </div>
          <div className={styles.heat}>
            {grid.map((row, oi) => (
              <div key={orders[oi]} className={styles.heatRow}>
                {row.map((v, ti) => (
                  <div
                    key={ti}
                    className={styles.cell}
                    title={`t=${times[ti]?.toFixed(4)} s · H${orders[oi]}: ${v.toFixed(3)}${
                      ch.unit ? ` ${ch.unit}` : ''
                    }`}
                    style={{ background: heatColor(v / maxVal) }}
                  />
                ))}
              </div>
            ))}
          </div>
        </div>
        <div className={styles.xAxis}>
          <span className="mono">{times[0]?.toFixed(3)} s</span>
          <span className="mono">{times[times.length - 1]?.toFixed(3)} s</span>
        </div>
      </div>
    </div>
  );
}
