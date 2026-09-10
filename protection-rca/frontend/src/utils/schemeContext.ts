import type { FaultClassification, ProtectionOperation } from '@/types';

/** True when distance / Z1·km location is in scope. */
export function isDistanceApplicable(opts: {
  fault?: FaultClassification | null;
  protection?: ProtectionOperation[] | null;
}): boolean {
  const { fault, protection } = opts;
  const feat = fault?.features as
    | {
        distance_applicable?: boolean;
        location_method?: string;
        distance_detail?: { status?: string };
      }
    | null
    | undefined;

  // Explicit backend flag wins (includes 87+21-backup and 87L+Z1 cases)
  if (feat?.distance_applicable === true) return true;
  if (feat?.distance_applicable === false) return false;
  const distStatus = String(feat?.distance_detail?.status || '').toUpperCase();
  if (distStatus === 'NOT_APPLICABLE') return false;

  const ops = protection ?? [];

  const isDiffBlob = (blob: string) =>
    /\b87[TBLG]?\b/.test(blob) || blob.includes('DIFFERENTIAL') || /BUS\s*ZONE/.test(blob);

  const isLineDiffBlob = (blob: string) =>
    /\b87L\b/.test(blob) || (blob.includes('DIFFERENTIAL') && blob.includes('LINE'));

  const isUnitDiffBlob = (blob: string) =>
    /\b87[BTG]\b/.test(blob) ||
    /BUS\s*ZONE/.test(blob) ||
    (blob.includes('BUS') && blob.includes('DIFF')) ||
    (blob.includes('TRANSFORMER') && blob.includes('DIFF'));

  const isDistBlob = (blob: string) =>
    /\b21\b/.test(blob) ||
    blob.includes('DISTANCE') ||
    /\bZ[123]\b/.test(blob) ||
    /ZONE\s*[123]\b/.test(blob);

  let distOperated = false;
  let distEnabled = false;
  let lineDiffOperated = false;
  let unitDiffOperated = false;

  for (const p of ops) {
    const blob = `${p.element ?? ''} ${p.function_code ?? ''} ${p.operation_type ?? ''}`.toUpperCase();
    const ot = String(p.operation_type || '').toUpperCase();
    const asserted = Boolean(p.asserted) || ot === 'TRIP' || ot === 'PICKUP' || ot === 'OPERATED';

    if (isDistBlob(blob) && !isDiffBlob(blob)) {
      // Assessment rows may mark enabled without asserted trip (backup 21)
      if (ot === 'ASSESSMENT' || asserted) distEnabled = true;
      if (asserted && ot !== 'ASSESSMENT') distOperated = true;
      if (p.asserted) distOperated = true;
      continue;
    }

    if (!asserted) continue;
    if (isLineDiffBlob(blob)) lineDiffOperated = true;
    else if (isUnitDiffBlob(blob)) unitDiffOperated = true;
    else if (isDiffBlob(blob)) unitDiffOperated = true;
  }

  if (distOperated) return true;
  // 87 primary + 21 backup enabled (common 87L21 / stepped-distance backup)
  if (distEnabled && (lineDiffOperated || unitDiffOperated)) return true;
  // Line differential alone: only unlock if backend already said so (needs Z1)
  if (lineDiffOperated && !unitDiffOperated) {
    // Without features flag we cannot see Z1 here — stay conservative
    return false;
  }
  return false;
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

const SCHEME_LABELS: Record<string, string> = {
  line_distance_stepped: 'Stepped distance (21)',
  line_diff_distance_backup: 'Line differential + distance backup',
  pilot_pott: 'Pilot POTT / permissive',
  feeder_oc_ef: 'Feeder OC / EF',
  xfmr_unit: 'Transformer unit (87T)',
  bus_unit: 'Bus differential (87B)',
  bf_cascade: 'Breaker failure (50BF)',
  gen_unit: 'Generator differential (87G)',
};

/** Display label for a scheme library id. */
export function schemeLabel(schemeId: string | null | undefined): string {
  if (!schemeId) return 'Scheme not identified';
  return SCHEME_LABELS[schemeId] || schemeId.replace(/_/g, ' ');
}
