/** R–X locus display rules — distance loops only, never for every scheme/fault. */

export type RxPointLike = {
  id: string;
  label: string;
  r: number;
  x: number;
  color: string;
};

function norm(s: string): string {
  return String(s || '')
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '');
}

/** Canonical loop tokens for a fault (order = preference). */
export function preferredLoopTokens(faultType: string | null | undefined): string[] {
  const ft = String(faultType || '').toUpperCase().replace(/[^A-Z]/g, '');
  switch (ft) {
    case 'AG':
      return ['LOOPAG', 'ZAG', 'PHASEA', 'ZA'];
    case 'BG':
      return ['LOOPBG', 'ZBG', 'PHASEB', 'ZB'];
    case 'CG':
      return ['LOOPCG', 'ZCG', 'PHASEC', 'ZC'];
    case 'AB':
    case 'ABG':
      return ['LOOPAB', 'ZAB'];
    case 'BC':
    case 'BCG':
      return ['LOOPBC', 'ZBC'];
    case 'CA':
    case 'CAG':
      return ['LOOPCA', 'ZCA'];
    case 'ABC':
    case 'ABCG':
      return ['LOOPAB', 'ZAB', 'LOOPBC', 'ZBC', 'LOOPCA', 'ZCA'];
    default:
      return [];
  }
}

/** @deprecated use preferredLoopTokens — kept for tests / callers */
export function preferredLoopIdsForFault(faultType: string | null | undefined): string[] {
  const ft = String(faultType || '').toUpperCase().replace(/[^A-Z]/g, '');
  switch (ft) {
    case 'AG':
      return ['loop_AG', 'ZAG', 'phase_A', 'ZA'];
    case 'BG':
      return ['loop_BG', 'ZBG', 'phase_B', 'ZB'];
    case 'CG':
      return ['loop_CG', 'ZCG', 'phase_C', 'ZC'];
    case 'AB':
    case 'ABG':
      return ['loop_AB', 'ZAB'];
    case 'BC':
    case 'BCG':
      return ['loop_BC', 'ZBC'];
    case 'CA':
    case 'CAG':
      return ['loop_CA', 'ZCA'];
    case 'ABC':
    case 'ABCG':
      return ['loop_AB', 'ZAB', 'loop_BC', 'ZBC', 'loop_CA', 'ZCA'];
    default:
      return [];
  }
}

/** Phases that belong on a distance-style R–X plot for this fault type. */
export function faultedPhasesForRx(faultType: string | null | undefined): Set<string> | null {
  const ft = String(faultType || '').toUpperCase().replace(/[^A-Z]/g, '');
  if (!ft || ft === 'UNKNOWN') return null;
  switch (ft) {
    case 'AG':
      return new Set(['A']);
    case 'BG':
      return new Set(['B']);
    case 'CG':
      return new Set(['C']);
    case 'AB':
    case 'ABG':
      return new Set(['A', 'B']);
    case 'BC':
    case 'BCG':
      return new Set(['B', 'C']);
    case 'CA':
    case 'CAG':
      return new Set(['C', 'A']);
    case 'ABC':
    case 'ABCG':
      return new Set(['A', 'B', 'C']);
    default:
      return null;
  }
}

export function isRxLocusApplicable(
  distanceApplicable: boolean | null | undefined,
  faultType?: string | null,
): boolean {
  if (distanceApplicable !== true) return false;
  return preferredLoopTokens(faultType).length > 0;
}

function pointTokens(p: RxPointLike): string[] {
  return [norm(p.id), norm(p.label)].filter(Boolean);
}

/** Keep the faulted loop impedance — prefer ZAB for ABG, not stray ZA/ZB. */
export function filterRxPointsForFault<T extends RxPointLike>(
  points: T[],
  faultType: string | null | undefined,
): T[] {
  const pref = preferredLoopTokens(faultType);
  if (!pref.length) return [];

  const ft = String(faultType || '').toUpperCase().replace(/[^A-Z]/g, '');
  const multi = ft === 'ABC' || ft === 'ABCG';

  const hits: T[] = [];
  for (const token of pref) {
    for (const p of points) {
      if (pointTokens(p).includes(token) && !hits.includes(p)) {
        hits.push(p);
        if (!multi) return hits.slice(0, 1);
      }
    }
  }
  if (hits.length) return multi ? hits.slice(0, 3) : hits.slice(0, 1);

  // SLG fallback: phase self-Z when loop_* not yet in stored analysis
  if (['AG', 'BG', 'CG'].includes(ft)) {
    const phases = faultedPhasesForRx(ft);
    if (!phases) return [];
    return points
      .filter((p) => {
        const toks = pointTokens(p);
        return [...phases].some(
          (ph) => toks.includes(`PHASE${ph}`) || toks.includes(`Z${ph}`),
        );
      })
      .slice(0, 1);
  }

  return [];
}

/** Keep measurement rows for the faulted impedance loop only. */
export function filterImpedanceRowsForFault<
  T extends { quantity?: string | null; phase?: string | null },
>(rows: T[], faultType: string | null | undefined): T[] {
  const pref = preferredLoopTokens(faultType);
  if (!pref.length) {
    // No classified fault — do not invent a filter; show nothing loop-specific
    const ft = String(faultType || '').toUpperCase().replace(/[^A-Z]/g, '');
    if (!ft || ft === 'UNKNOWN') return rows;
    return [];
  }

  const ft = String(faultType || '').toUpperCase().replace(/[^A-Z]/g, '');
  const multi = ft === 'ABC' || ft === 'ABCG';

  const rowTokens = (m: T): string[] => {
    const q = norm(String(m.quantity || ''));
    const p = norm(String(m.phase || ''));
    const out = [q, p].filter(Boolean);
    // Z_AG → ZAG, ZAG → ZAG, phase AG → AG
    if (q.startsWith('Z')) out.push(q);
    if (p && !out.includes(`Z${p}`)) out.push(`Z${p}`);
    return out;
  };

  const hits: T[] = [];
  for (const token of pref) {
    for (const m of rows) {
      if (hits.includes(m)) continue;
      const toks = rowTokens(m);
      if (toks.includes(token) || toks.includes(token.replace(/^LOOP/, 'Z'))) {
        hits.push(m);
        if (!multi) {
          // Prefer first preferred token only (e.g. ZAG over ZA)
          return hits.slice(0, 1);
        }
      }
    }
    if (!multi && hits.length) return hits.slice(0, 1);
  }
  return multi ? hits.slice(0, 3) : hits.slice(0, 1);
}

export function rxLocusEmptyHint(
  distanceApplicable: boolean | null | undefined,
  faultType?: string | null,
): string {
  if (distanceApplicable !== true) {
    return 'R–X locus not applicable for this scheme (distance / 21 context only).';
  }
  const ft = String(faultType || 'UNKNOWN').toUpperCase();
  if (!ft || ft === 'UNKNOWN') {
    return 'R–X locus needs a classified fault type (AG/BG/CG/AB/…).';
  }
  const ids = preferredLoopIdsForFault(ft);
  const lab = (ids[0] || 'faulted loop').replace('loop_', 'Z');
  return `No ${lab} impedance for the faulted loop — re-run analysis.`;
}
