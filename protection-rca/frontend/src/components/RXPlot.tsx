import { useEffect, useRef } from 'react';
import styles from './PhasorDiagram.module.css';

export interface RXPoint {
  id: string;
  label: string;
  r: number;
  x: number;
  color: string;
}

/** Legacy mho circle along positive R (reach diameter). */
export interface ZoneCircle {
  label: string;
  reachOhm: number;
  color: string;
  shape?: 'reach';
}

/** Real RIO/XRIO / settings zone: mho disk or polygon. */
export interface ZoneGeometry {
  label: string;
  color: string;
  shape: 'mho' | 'polygon' | 'reach';
  /** mho */
  centerR?: number;
  centerX?: number;
  radiusOhm?: number;
  /** legacy reach-diameter circle on R axis */
  reachOhm?: number;
  /** polygon vertices in ohms */
  polygon?: Array<{ r: number; x: number }>;
}

export type ZoneSpec = ZoneCircle | ZoneGeometry;

interface Props {
  title?: string;
  points: RXPoint[];
  zones?: ZoneSpec[];
  size?: number;
  emptyHint?: string;
}

function zoneExtents(z: ZoneSpec): number[] {
  const out: number[] = [];
  if ('shape' in z && z.shape === 'mho' && z.centerR != null && z.radiusOhm != null) {
    out.push(Math.hypot(z.centerR, z.centerX ?? 0) + z.radiusOhm);
  } else if ('shape' in z && z.shape === 'polygon' && z.polygon?.length) {
    for (const p of z.polygon) out.push(Math.hypot(p.r, p.x));
  } else if (typeof (z as ZoneCircle).reachOhm === 'number') {
    out.push((z as ZoneCircle).reachOhm);
  }
  return out;
}

function drawZone(
  ctx: CanvasRenderingContext2D,
  z: ZoneSpec,
  cx: number,
  cy: number,
  scale: number,
) {
  ctx.strokeStyle = z.color;
  ctx.setLineDash([4, 3]);
  ctx.lineWidth = 1.5;

  if ('shape' in z && z.shape === 'mho' && z.centerR != null && z.radiusOhm != null) {
    const zx = cx + z.centerR * scale;
    const zy = cy - (z.centerX ?? 0) * scale;
    const rPx = z.radiusOhm * scale;
    ctx.beginPath();
    ctx.arc(zx, zy, rPx, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = z.color;
    ctx.fillText(z.label, zx - 10, zy - rPx - 4);
    return;
  }

  if ('shape' in z && z.shape === 'polygon' && z.polygon && z.polygon.length >= 3) {
    ctx.beginPath();
    z.polygon.forEach((p, i) => {
      const x = cx + p.r * scale;
      const y = cy - p.x * scale;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.stroke();
    ctx.setLineDash([]);
    const mid = z.polygon[0];
    ctx.fillStyle = z.color;
    ctx.fillText(z.label, cx + mid.r * scale + 4, cy - mid.x * scale - 4);
    return;
  }

  const reach = (z as ZoneCircle).reachOhm;
  if (typeof reach === 'number' && reach > 0) {
    const rPx = (reach / 2) * scale;
    const zx = cx + rPx;
    ctx.beginPath();
    ctx.arc(zx, cy, rPx, 0, Math.PI * 2);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = z.color;
    ctx.fillText(z.label, zx - 10, cy - rPx - 4);
  }
}

export function RXPlot({
  title = 'R–X locus',
  points,
  zones = [],
  size = 280,
  emptyHint = 'No impedance points available.',
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

    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, css, css);

    const cx = css / 2;
    const cy = css / 2;
    const maxAbs = Math.max(
      1,
      ...points.map((p) => Math.hypot(p.r, p.x)),
      ...zones.flatMap(zoneExtents),
    );
    const scale = (css * 0.38) / maxAbs;

    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(20, cy);
    ctx.lineTo(css - 20, cy);
    ctx.moveTo(cx, 20);
    ctx.lineTo(cx, css - 20);
    ctx.stroke();

    ctx.fillStyle = text;
    ctx.font = '11px Consolas, Courier New, monospace';
    ctx.fillText('R (Ω)', css - 42, cy - 6);
    ctx.fillText('X (Ω)', cx + 6, 16);

    zones.forEach((z) => drawZone(ctx, z, cx, cy, scale));

    points.forEach((p) => {
      const x = cx + p.r * scale;
      const y = cy - p.x * scale;
      ctx.fillStyle = p.color;
      ctx.beginPath();
      ctx.arc(x, y, 5, 0, Math.PI * 2);
      ctx.fill();
      ctx.fillText(p.label, x + 7, y - 4);
    });
  }, [points, zones, size]);

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
