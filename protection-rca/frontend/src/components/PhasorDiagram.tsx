import { useEffect, useRef } from 'react';
import styles from './PhasorDiagram.module.css';

export interface PhasorVector {
  id: string;
  label: string;
  mag: number;
  angleDeg: number;
  unit?: string;
  color: string;
}

interface Props {
  title: string;
  vectors: PhasorVector[];
  size?: number;
  emptyHint?: string;
}

/** Distinct hues — one per arrow so same-phase channels stay distinguishable. */
const DISTINCT_COLORS = [
  '#e07020',
  '#2aaa55',
  '#2a8fd4',
  '#c47a00',
  '#8b5cf6',
  '#db2777',
  '#0d9488',
  '#dc2626',
  '#2563eb',
  '#ca8a04',
  '#059669',
  '#7c3aed',
  '#ea580c',
  '#4f46e5',
  '#be185d',
  '#0891b2',
];

function uniqueColors(vectors: PhasorVector[]): string[] {
  const used = new Set<string>();
  return vectors.map((v, i) => {
    let c = (v.color || '').toLowerCase();
    if (!c || used.has(c)) {
      c = DISTINCT_COLORS[i % DISTINCT_COLORS.length];
      for (let k = 0; k < DISTINCT_COLORS.length; k++) {
        const cand = DISTINCT_COLORS[(i + k) % DISTINCT_COLORS.length];
        if (!used.has(cand)) {
          c = cand;
          break;
        }
      }
    }
    used.add(c);
    return c;
  });
}

function draw(
  canvas: HTMLCanvasElement,
  vectors: PhasorVector[],
  theme: { bg: string; grid: string; text: string },
) {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const dpr = window.devicePixelRatio || 1;
  const css = canvas.clientWidth || 280;
  canvas.width = css * dpr;
  canvas.height = css * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const cx = css / 2;
  const cy = css / 2;
  const R = css * 0.38;

  ctx.fillStyle = theme.bg;
  ctx.fillRect(0, 0, css, css);

  ctx.strokeStyle = theme.grid;
  ctx.lineWidth = 1;
  for (const f of [0.33, 0.66, 1]) {
    ctx.beginPath();
    ctx.arc(cx, cy, R * f, 0, Math.PI * 2);
    ctx.stroke();
  }

  ctx.beginPath();
  ctx.moveTo(cx - R - 8, cy);
  ctx.lineTo(cx + R + 8, cy);
  ctx.moveTo(cx, cy - R - 8);
  ctx.lineTo(cx, cy + R + 8);
  ctx.stroke();

  ctx.fillStyle = theme.text;
  ctx.font = '11px Consolas, Courier New, monospace';
  ctx.textAlign = 'left';
  ctx.fillText('0°', cx + R + 4, cy - 4);
  ctx.fillText('90°', cx + 4, cy - R - 4);

  const maxMag = Math.max(...vectors.map((v) => Math.abs(v.mag)), 1e-9);
  const colors = uniqueColors(vectors);

  // Many channels → clean arrows only; identify via colour + numbered legend
  // Few channels → small tip number (skip near-zero so origin stays clear)
  const showTipNumbers = vectors.length <= 5;
  const tipMinFrac = 0.12;

  const order = vectors
    .map((v, i) => ({ v, i, mag: Math.abs(v.mag) }))
    .sort((a, b) => b.mag - a.mag);

  for (const { v, i } of order) {
    const color = colors[i];
    const frac = Math.abs(v.mag) / maxMag;
    const scale = frac * R;
    const rad = (-v.angleDeg * Math.PI) / 180;
    const tipX = cx + scale * Math.cos(rad);
    const tipY = cy + scale * Math.sin(rad);

    ctx.strokeStyle = color;
    ctx.fillStyle = color;
    ctx.lineWidth = vectors.length > 10 ? 1.8 : 2.2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(tipX, tipY);
    ctx.stroke();

    const ah = 7;
    const ang = Math.atan2(tipY - cy, tipX - cx);
    ctx.beginPath();
    ctx.moveTo(tipX, tipY);
    ctx.lineTo(tipX - ah * Math.cos(ang - 0.4), tipY - ah * Math.sin(ang - 0.4));
    ctx.lineTo(tipX - ah * Math.cos(ang + 0.4), tipY - ah * Math.sin(ang + 0.4));
    ctx.closePath();
    ctx.fill();

    if (!showTipNumbers || frac < tipMinFrac) continue;

    const badgeR = 8;
    const bx = tipX + (badgeR + 3) * Math.cos(ang);
    const by = tipY + (badgeR + 3) * Math.sin(ang);
    ctx.beginPath();
    ctx.arc(bx, by, badgeR, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 1.25;
    ctx.stroke();
    ctx.fillStyle = '#fff';
    ctx.font = '700 10px Consolas, Courier New, monospace';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(String(i + 1), bx, by + 0.5);
  }

  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
}

export function PhasorDiagram({ title, vectors, size = 280, emptyHint }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);
  const colors = uniqueColors(vectors);
  const crowded = vectors.length > 5;

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas || !vectors.length) return;

    const read = (name: string, fallback: string) =>
      getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

    const paint = () =>
      draw(canvas, vectors, {
        bg: read('--bg-elevated', '#f7f9fc'),
        grid: read('--border', '#e2e8f0'),
        text: read('--text-muted', '#64748b'),
      });

    paint();
    const ro = new ResizeObserver(paint);
    ro.observe(canvas);
    return () => ro.disconnect();
  }, [vectors]);

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>{title}</div>
      {!vectors.length ? (
        <div className={styles.empty}>{emptyHint ?? 'No phasor angles available.'}</div>
      ) : (
        <div className={styles.body}>
          <canvas ref={ref} className={styles.canvas} style={{ width: size, height: size }} />
          <ul className={styles.legend}>
            <li className={styles.legendHint}>
              {crowded
                ? 'Identify by colour number in this list (plot kept clear)'
                : 'Number on plot matches this list'}
            </li>
            {vectors.map((v, i) => (
              <li key={v.id}>
                <span className={styles.idx} style={{ color: colors[i], borderColor: colors[i] }}>
                  {i + 1}
                </span>
                <span className={styles.swatch} style={{ background: colors[i] }} aria-hidden />
                <span className="mono" title={v.label}>
                  {v.label}
                </span>
                <span className={`mono ${styles.vals}`}>
                  {v.mag.toFixed(3)}
                  {v.unit ? ` ${v.unit}` : ''} ∠ {v.angleDeg.toFixed(1)}°
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
