import type { ZoneGeometry } from '@/components/RXPlot';

const ZONE_COLORS = ['#c45a12', '#5b9fd4', '#2aaa55', '#c47a00', '#8b5cf6'];

export interface RawDistanceZone {
  label?: string;
  shape?: string;
  center_r?: number | null;
  center_x?: number | null;
  radius_ohm?: number | null;
  reach_ohm?: number | null;
  polygon?: Array<{ r?: number; x?: number }> | null;
}

/** Map backend `distance_zones` (RIO/XRIO/settings) into RXPlot zone specs. */
export function mapDistanceZonesToPlot(raw: unknown): ZoneGeometry[] {
  if (!Array.isArray(raw) || !raw.length) return [];
  const out: ZoneGeometry[] = [];
  raw.forEach((z, i) => {
    if (!z || typeof z !== 'object') return;
    const zone = z as RawDistanceZone;
    const label = String(zone.label || `Z${i + 1}`);
    const color = ZONE_COLORS[i % ZONE_COLORS.length];
    const shape = String(zone.shape || '').toLowerCase();

    if (shape === 'polygon' && Array.isArray(zone.polygon) && zone.polygon.length >= 3) {
      const poly = zone.polygon
        .map((p) => ({
          r: typeof p?.r === 'number' ? p.r : NaN,
          x: typeof p?.x === 'number' ? p.x : NaN,
        }))
        .filter((p) => Number.isFinite(p.r) && Number.isFinite(p.x));
      if (poly.length >= 3) {
        out.push({ label, color, shape: 'polygon', polygon: poly });
        return;
      }
    }

    if (
      shape === 'mho' &&
      typeof zone.center_r === 'number' &&
      typeof zone.radius_ohm === 'number' &&
      zone.radius_ohm > 0
    ) {
      out.push({
        label,
        color,
        shape: 'mho',
        centerR: zone.center_r,
        centerX: typeof zone.center_x === 'number' ? zone.center_x : 0,
        radiusOhm: zone.radius_ohm,
        reachOhm: typeof zone.reach_ohm === 'number' ? zone.reach_ohm : undefined,
      });
      return;
    }

    if (typeof zone.reach_ohm === 'number' && zone.reach_ohm > 0) {
      out.push({
        label,
        color,
        shape: 'reach',
        reachOhm: zone.reach_ohm,
      });
    }
  });
  return out;
}

/** Prefer event.extra.distance_zones, else report_analysis.distance_zones. */
export function loadEventDistanceZones(extra: Record<string, unknown> | undefined): ZoneGeometry[] {
  if (!extra) return [];
  const top = mapDistanceZonesToPlot(extra.distance_zones);
  if (top.length) return top;
  const ra = (extra.report_analysis || {}) as Record<string, unknown>;
  return mapDistanceZonesToPlot(ra.distance_zones);
}
