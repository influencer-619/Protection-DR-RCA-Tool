import { useEffect, useRef } from 'react';
import styles from './PhasorDiagram.module.css';

export interface DiffIrPoint {
  id: string;
  label: string;
  /** Restraint current Ir (x-axis), A or pu */
  restraint: number;
  /** Operate / differential current Id (y-axis) */
  operate: number;
  color?: string;
  operated?: boolean | null;
}

interface Props {
  title?: string;
  points: DiffIrPoint[];
  /** Slope k of percentage characteristic Id = Ip + k·Ir */
  slope?: number;
  /** Minimum operate pickup Ip */
  pickup?: number;
  size?: number;
  emptyHint?: string;
}

/**
 * SIGRA-style differential operate/restraint characteristic (Id vs Ir).
 * Straight-line percentage slope for indication — not a substitute for vendor bias curve.
 */
export function DiffIrPlot({
  title = 'Differential Id / Ir',
  points,
  slope = 0.3,
  pickup = 0.2,
  size = 280,
  emptyHint = 'Differential Id/Ir not available (needs 87 currents or assessment).',
}: Props) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const css = canvas.clientWidth || size;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = css * dpr;
    canvas.height = css * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const bg =
      getComputedStyle(document.documentElement).getPropertyValue('--panel-bg').trim() || '#121820';
    const grid =
      getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#2a3544';
    const text =
      getComputedStyle(document.documentElement).getPropertyValue('--text-muted').trim() || '#9aabbd';
    const accent =
      getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#c45a12';

    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, css, css);

    const pad = 36;
    const maxIr = Math.max(
      pickup * 4,
      ...points.map((p) => Math.abs(p.restraint)),
      1,
    );
    const maxId = Math.max(
      pickup + slope * maxIr,
      ...points.map((p) => Math.abs(p.operate)),
      pickup * 2,
      1,
    );
    const x0 = pad;
    const y0 = css - pad;
    const plotW = css - pad * 2;
    const plotH = css - pad * 2;
    const sx = plotW / maxIr;
    const sy = plotH / maxId;

    // Axes
    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x0, pad);
    ctx.lineTo(x0, y0);
    ctx.lineTo(css - pad, y0);
    ctx.stroke();

    ctx.fillStyle = text;
    ctx.font = '11px Consolas, Courier New, monospace';
    ctx.fillText('Ir', css - pad - 14, y0 - 6);
    ctx.fillText('Id', x0 + 4, pad + 10);

    // Percentage characteristic Id = Ip + k·Ir
    ctx.strokeStyle = accent;
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(x0, y0 - pickup * sy);
    ctx.lineTo(x0 + maxIr * sx, y0 - (pickup + slope * maxIr) * sy);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = accent;
    ctx.fillText(`Id=Ip+k·Ir (k=${slope.toFixed(2)}, Ip=${pickup.toFixed(2)})`, x0 + 8, pad + 24);

    // Operating region hint (above line)
    ctx.fillStyle = 'rgba(196, 90, 18, 0.08)';
    ctx.beginPath();
    ctx.moveTo(x0, y0 - pickup * sy);
    ctx.lineTo(x0 + maxIr * sx, y0 - (pickup + slope * maxIr) * sy);
    ctx.lineTo(x0 + maxIr * sx, pad);
    ctx.lineTo(x0, pad);
    ctx.closePath();
    ctx.fill();

    points.forEach((p) => {
      const x = x0 + Math.max(0, p.restraint) * sx;
      const y = y0 - Math.max(0, p.operate) * sy;
      ctx.fillStyle = p.color || (p.operated ? '#e07020' : '#2aaa55');
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillStyle = text;
      ctx.fillText(p.label, x + 7, y - 4);
    });
  }, [points, slope, pickup, size]);

  return (
    <div className={styles.wrap}>
      <div className={styles.title}>{title}</div>
      {!points.length ? (
        <div className={styles.empty}>{emptyHint}</div>
      ) : (
        <canvas ref={ref} className={styles.canvas} style={{ width: '100%', maxWidth: size, aspectRatio: '1' }} />
      )}
    </div>
  );
}
