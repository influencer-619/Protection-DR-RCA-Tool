import type { FaultClassification, ProtectionOperation } from '@/types';

/** True when distance / Z1·km location is in scope (not every AG/OC/EF event). */
export function isDistanceApplicable(opts: {
  fault?: FaultClassification | null;
  protection?: ProtectionOperation[] | null;
}): boolean {
  const { fault, protection } = opts;
  if (fault?.distance_km != null && Number.isFinite(Number(fault.distance_km))) {
    return true;
  }
  const feat = fault?.features as
    | {
        distance_applicable?: boolean;
        location_method?: string;
        distance_detail?: { status?: string };
      }
    | null
    | undefined;
  if (feat?.distance_applicable === true) return true;
  if (feat?.distance_applicable === false) return false;
  const distStatus = String(feat?.distance_detail?.status || '').toUpperCase();
  if (distStatus === 'NOT_APPLICABLE') return false;

  // Only treat as distance context when a distance element actually operated
  const ops = protection ?? [];
  return ops.some((p) => {
    if (!p.asserted && String(p.operation_type || '').toUpperCase() === 'ASSESSMENT') {
      return false;
    }
    const blob = `${p.element ?? ''} ${p.function_code ?? ''} ${p.operation_type ?? ''}`.toUpperCase();
    const isDist =
      /\b21\b/.test(blob) ||
      blob.includes('DISTANCE') ||
      /\bZ[123]\b/.test(blob) ||
      blob.includes('ZONE');
    if (!isDist) return false;
    const ot = String(p.operation_type || '').toUpperCase();
    return p.asserted || ot === 'TRIP' || ot === 'PICKUP' || ot === 'OPERATED';
  });
}

/** Strip distance / Z1 limitation lines for non-distance cases (legacy persisted text). */
export function filterDistanceLimitations(
  text: string | null | undefined,
  distanceApplicable: boolean,
): string {
  if (!text) return '';
  if (distanceApplicable) return text;
  return text
    .split(/;\s*/)
    .map((s) => s.trim())
    .filter(
      (s) =>
        s &&
        !/FAULT\s*DISTANCE/i.test(s) &&
        !/Z1\s*\/\s*km/i.test(s) &&
        !/line Z1/i.test(s) &&
        !/Fault location shown only when/i.test(s),
    )
    .join('; ');
}

/** Human label for operated protection summary (scheme-agnostic). */
export function formatOperatedElements(ops: ProtectionOperation[]): string {
  const asserted = ops.filter((p) => p.asserted);
  if (!asserted.length) return 'None asserted / not mapped';
  return asserted
    .map((p) => {
      const code = p.function_code ? ` (${p.function_code})` : '';
      return `${p.element}${code} ${p.operation_type}`.trim();
    })
    .join('; ');
}
