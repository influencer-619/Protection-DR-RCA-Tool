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

  // Circles
  ctx.strokeStyle = theme.grid;
  ctx.lineWidth = 1;
  for (const f of [0.33, 0.66, 1]) {
    ctx.beginPath();
    ctx.arc(cx, cy, R * f, 0, Math.PI * 2);
    ctx.stroke();
  }

  // Axes
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

  for (const v of vectors) {
    const scale = (Math.abs(v.mag) / maxMag) * R;
    // Engineering convention: 0° on +X, angles counterclockwise from real axis
    const rad = (-v.angleDeg * Math.PI) / 180;
    const x = cx + scale * Math.cos(rad);
    const y = cy + scale * Math.sin(rad);

    ctx.strokeStyle = v.color;
    ctx.fillStyle = v.color;
    ctx.lineWidth = 2.2;
    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.lineTo(x, y);
    ctx.stroke();

    // Arrow head
    const ah = 8;
    const ang = Math.atan2(y - cy, x - cx);
    ctx.beginPath();
    ctx.moveTo(x, y);
    ctx.lineTo(x - ah * Math.cos(ang - 0.4), y - ah * Math.sin(ang - 0.4));
    ctx.lineTo(x - ah * Math.cos(ang + 0.4), y - ah * Math.sin(ang + 0.4));
    ctx.closePath();
    ctx.fill();

    ctx.font = '600 11px Segoe UI, Tahoma, sans-serif';
    ctx.fillText(v.label, x + 6, y - 4);
  }
}

export function PhasorDiagram({ title, vectors, size = 280, emptyHint }: Props) {
  const ref = useRef<HTMLCanvasElement>(null);

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
            {vectors.map((v) => (
              <li key={v.id}>
                <span className={styles.swatch} style={{ background: v.color }} />
                <span className="mono">{v.label}</span>
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
