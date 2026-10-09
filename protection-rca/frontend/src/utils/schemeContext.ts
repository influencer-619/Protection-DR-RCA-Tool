import type { FaultClassification, ProtectionOperation } from '@/types';
import { isEvidenceBackedAssert } from '@/utils/protectionOperateEvidence';
import { formatAnsi, formatAnsiCompact } from '@/utils/ansiDeviceNames';

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
    // Operated = evidence-backed assert only (not SOE / settings-only)
    const asserted = isEvidenceBackedAssert(p);

    if (isDistBlob(blob) && !isDiffBlob(blob)) {
      // Assessment rows may mark enabled without asserted trip (backup 21)
      if (ot === 'ASSESSMENT' || asserted || p.asserted) distEnabled = true;
      if (asserted) distOperated = true;
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
  const asserted = ops.filter((p) => isEvidenceBackedAssert(p));
  if (!asserted.length) return 'None asserted / not mapped';
  return asserted
    .map((p) => {
      const el = formatAnsiCompact(p.element);
      const nameHint = formatAnsi(p.element);
      const ot = String(p.operation_type || '').trim();
      return ot ? `${el} ${ot}` : el || nameHint;
    })
    .join(' · ');
}

/**
 * Scheme hint for bay one-line — same asserted elements as analysis "Operated",
 * including PICKUP/TRIP so the marker can match Protect / Conclude.
 */
export function baySchemeHintFromProtection(
  ops: ProtectionOperation[] | null | undefined,
): string | null {
  const asserted = (ops ?? []).filter((p) => isEvidenceBackedAssert(p));
  if (!asserted.length) return null;
  return asserted
    .map((p) => {
      const el = String(p.element || p.function_code || '').trim();
      const ot = String(p.operation_type || '').trim().toUpperCase();
      if (!el) return '';
      return ot ? `${el} ${ot}` : el;
    })
    .filter(Boolean)
    .join(' ');
}

/** Fallback when live protection API is empty — read persisted analysis assessments. */
export function schemeHintFromReportAnalysis(
  reportAnalysis: Record<string, unknown> | null | undefined,
): string | null {
  if (!reportAnalysis) return null;
  const nested = reportAnalysis.protection as
    | { assessments?: Array<Record<string, unknown>> }
    | undefined;
  const raw =
    (reportAnalysis.protection_assessment as Array<Record<string, unknown>> | undefined) ||
    (reportAnalysis.protection_assessments as Array<Record<string, unknown>> | undefined) ||
    nested?.assessments ||
    [];
  if (!Array.isArray(raw) || !raw.length) return null;
  const parts = raw
    .filter((a) => a.trip === true || a.pickup === true)
    .map((a) => {
      const el = String(a.element || '').trim();
      if (!el) return '';
      const op =
        a.trip === true ? (a.pickup === true ? 'PICKUP TRIP' : 'TRIP') : 'PICKUP';
      return `${el} ${op}`;
    })
    .filter(Boolean);
  return parts.length ? parts.join(' ') : null;
}

/**
 * Single resolver for bay one-line / scheme template across Setup, Analyse, Summary.
 * Live protection wins; persisted analysis is fallback only.
 */
export function resolveBaySchemeHint(opts: {
  protection?: ProtectionOperation[] | null;
  reportAnalysis?: Record<string, unknown> | null;
  eventExtra?: Record<string, unknown> | null;
}): string | null {
  const fromLive = baySchemeHintFromProtection(opts.protection);
  if (fromLive) return fromLive;
  const ra =
    opts.reportAnalysis ||
    ((opts.eventExtra?.report_analysis as Record<string, unknown> | undefined) ?? null);
  return schemeHintFromReportAnalysis(ra);
}

export function faultTypeFromReportAnalysis(
  reportAnalysis: Record<string, unknown> | null | undefined,
): string | null {
  if (!reportAnalysis) return null;
  const fc = reportAnalysis.fault_classification;
  if (fc && typeof fc === 'object' && fc !== null) {
    const ft = (fc as { fault_type?: unknown }).fault_type;
    if (typeof ft === 'string' && ft.trim()) return ft;
  }
  return null;
}

/** Prefer live fault classification over denormalized event.fault_type. */
export function bayFaultTypeFromAnalysis(
  fault?: FaultClassification | null,
  eventFaultType?: string | null,
): string | null {
  if (fault?.fault_type) return String(fault.fault_type);
  return eventFaultType ? String(eventFaultType) : null;
}

/**
 * Fault type sync across Overview / DR / Electrical / Summary / header.
 * Priority: live FaultClassification → report_analysis → event.fault_type.
 */
export function resolveFaultType(opts: {
  fault?: FaultClassification | null;
  eventFaultType?: string | null;
  reportAnalysis?: Record<string, unknown> | null;
  eventExtra?: Record<string, unknown> | null;
}): string | null {
  if (opts.fault?.fault_type) return String(opts.fault.fault_type);
  const ra =
    opts.reportAnalysis ||
    ((opts.eventExtra?.report_analysis as Record<string, unknown> | undefined) ?? null);
  const fromRa = faultTypeFromReportAnalysis(ra);
  if (fromRa) return fromRa;
  return opts.eventFaultType ? String(opts.eventFaultType) : null;
}

/** Explicit distance flag from persisted analysis, or null if unknown. */
export function distanceApplicableFromReportAnalysis(
  reportAnalysis: Record<string, unknown> | null | undefined,
): boolean | null {
  if (!reportAnalysis) return null;
  const fc = reportAnalysis.fault_classification;
  if (!fc || typeof fc !== 'object') return null;
  const f = fc as {
    evidence?: { distance_applicable?: unknown };
    features?: { distance_applicable?: unknown };
    distance?: { status?: unknown };
  };
  const ev = f.evidence || f.features || {};
  const status = String(f.distance?.status || '').toUpperCase();
  if (ev.distance_applicable === true && status !== 'NOT_APPLICABLE') return true;
  if (ev.distance_applicable === false || status === 'NOT_APPLICABLE') return false;
  return null;
}

/**
 * Distance applicability sync — report_analysis flag first, else live fault/protection.
 */
export function resolveDistanceApplicable(opts: {
  fault?: FaultClassification | null;
  protection?: ProtectionOperation[] | null;
  reportAnalysis?: Record<string, unknown> | null;
  eventExtra?: Record<string, unknown> | null;
}): boolean {
  const ra =
    opts.reportAnalysis ||
    ((opts.eventExtra?.report_analysis as Record<string, unknown> | undefined) ?? null);
  const fromRa = distanceApplicableFromReportAnalysis(ra);
  if (fromRa !== null) return fromRa;
  return isDistanceApplicable({
    fault: opts.fault,
    protection: opts.protection,
  });
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
