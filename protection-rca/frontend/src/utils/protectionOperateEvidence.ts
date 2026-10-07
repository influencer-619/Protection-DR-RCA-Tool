import type { ProtectionOperation } from '@/types';

/**
 * True when a protection op has industry-grade operate evidence:
 * COMTRADE digital channel name, or relay SER (`ser:…`) / event report (`report:…`).
 * Bare station SOE (`soe:…`) and PHYS-* physics tags do not count.
 */
export function hasDigitalOperateEvidence(
  p: ProtectionOperation | null | undefined,
): boolean {
  if (!p) return false;
  const d = (p.details || {}) as Record<string, unknown>;
  const evid =
    (d.evidence_ids as unknown[]) ||
    (d.channel_evidence as unknown[]) ||
    ((d.metadata as Record<string, unknown> | undefined)?.channel_evidence as unknown[]) ||
    ((d.metadata as Record<string, unknown> | undefined)?.operate_channels as unknown[]) ||
    [];
  if (!Array.isArray(evid) || !evid.length) return false;
  return evid.some((e) => {
    const s = String(e || '').trim();
    if (!s) return false;
    const low = s.toLowerCase();
    if (s.toUpperCase().startsWith('PHYS-')) return false;
    // Station SOE without ser:/report: upgrade — context only
    if (low.startsWith('soe:') && !low.startsWith('ser:')) return false;
    return true;
  });
}

/** Asserted trip/pickup backed by COMTRADE digital or clear relay SER/report. */
export function isEvidenceBackedAssert(p: ProtectionOperation): boolean {
  if (!p.asserted) return false;
  const ot = String(p.operation_type || '').toUpperCase();
  if (ot === 'ASSESSMENT') return false;
  return hasDigitalOperateEvidence(p);
}
