import { formatAnsiCompact } from '@/utils/ansiDeviceNames';
import styles from './OneLineBay.module.css';

export type BaySchemeKind =
  | 'line_distance'
  | 'line_diff'
  | 'transformer_diff'
  | 'bus_diff'
  | 'generator_diff'
  | 'feeder_oc';

interface Props {
  substation?: string | null;
  bay?: string | null;
  relay?: string | null;
  feeder?: string | null;
  faultType?: string | null;
  distanceKm?: number | null;
  lineLengthKm?: number | null;
  /** When false, never show km (differential / OC cases). */
  distanceApplicable?: boolean;
  /** Optional protection hint e.g. 87T / 87G,87T */
  schemeHint?: string | null;
  /** Navigate to DR / waveforms when bay schematic is activated. */
  onOpenDr?: () => void;
  /** Combined cascade / multi-end labels for dual-end context. */
  cascadeEnds?: {
    mode: 'cascade' | 'line';
    leftRole: string;
    leftLabel: string;
    rightRole: string;
    rightLabel: string;
  } | null;
}

/** ANSI / IEC function codes from a scheme hint (50BF, 67N, 21P, 87T, …). */
export function extractOperatedCodes(schemeHint?: string | null): string[] {
  if (!schemeHint) return [];
  const tokens = schemeHint
    .toUpperCase()
    .split(/[\s,;/|]+/)
    .map((t) => t.trim())
    .filter(Boolean);
  const codes: string[] = [];
  for (const t of tokens) {
    // 50BF, 51N, 67P, 21G, 87T, 87G, 50P, 51, 21, 79 …
    if (/^\d{2}[A-Z]{0,3}$/.test(t)) codes.push(t);
  }
  // Prefer BF / differential / distance ahead of plain OC in the marker
  const rank = (c: string) => {
    if (/^50BF|^62BF|^BF/.test(c)) return 0;
    if (/^87/.test(c)) return 1;
    if (/^21/.test(c)) return 2;
    if (/^67/.test(c)) return 3;
    if (/^50|^51/.test(c)) return 4;
    return 5;
  };
  return [...new Set(codes)].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

/** Infer schematic template from bay / relay / operated elements (industry SLD practice). */
export function inferBaySchemeKind(opts: {
  bay?: string | null;
  relay?: string | null;
  feeder?: string | null;
  schemeHint?: string | null;
  distanceApplicable?: boolean;
}): BaySchemeKind {
  const bay = (opts.bay || '').toUpperCase();
  const hint = (opts.schemeHint || '').toUpperCase();
  const blob = `${bay} ${opts.relay || ''} ${opts.feeder || ''} ${hint}`.toUpperCase();
  const has87 = /\b87[TBLG]?\b/.test(hint) || /\b87[TBLG]?\b/.test(blob);
  const xfmrBay = /\bPTR\b|\bTRF\b|\bXFMR\b|TRANSFORMER/.test(bay);
  const diffHint =
    /\b87T\b/.test(hint) ||
    /TRANSFORMER\s*DIFF|DIFFERENTIAL/.test(hint) ||
    /\bIDIFF\b|\bIREST\b/.test(hint);
  const bfOnly =
    /\b50BF\b|\b62BF\b|\bLBB\b/.test(hint) &&
    !/\b87[TBLG]?\b/.test(hint) &&
    !/\b21\b/.test(hint);

  if (/\b87B\b/.test(hint) || /BUS\s*ZONE|BUS\s*DIFF/.test(hint)) return 'bus_diff';
  // Transformer differential only when protection evidence says so — not bay name alone
  // (PTR bay + station-tie OC COMTRADE must not draw a fake 87T zone).
  if (diffHint || (/\b87T\b/.test(hint) && xfmrBay)) {
    return 'transformer_diff';
  }
  if (/\b87L\b/.test(hint) || /LINE\s*DIFF/.test(hint)) return 'line_diff';
  if (/\b87G\b/.test(hint) && /GENERATOR|\bGEN\b|\bGSU\b/.test(blob)) return 'generator_diff';
  // Siemens 7UT REF (87G) on a transformer bay with differential context
  if (/\b87G\b/.test(hint) && (xfmrBay || diffHint || has87)) {
    return 'transformer_diff';
  }
  if (has87 && xfmrBay && !opts.distanceApplicable) return 'transformer_diff';
  // BF / LBB / feeder OC must not draw a distance line even on a line bay name
  if (bfOnly || /\b50P\b|\b51P\b|\b50N\b|\b51N\b|\b67P\b|\b67N\b/.test(hint)) {
    if (!opts.distanceApplicable) return 'feeder_oc';
  }
  if (opts.distanceApplicable) return 'line_distance';
  return 'feeder_oc';
}

/** Phase involvement ticks from classified fault type (AB, AG, ABCG, …). */
export function faultPhases(faultType?: string | null): ('A' | 'B' | 'C' | 'G')[] {
  const raw = (faultType || '').toUpperCase().trim();
  if (!raw || raw === 'UNKNOWN' || raw === 'INCONCLUSIVE' || raw === 'NONE') return [];
  // Normalise "A-B", "AB-G", "3PH" styles
  let u = raw.replace(/[^A-Z0-9]/g, '');
  if (/^(3PH|ABC|ABCG|THREEPHASE)$/.test(u)) {
    return u.includes('G') ? ['A', 'B', 'C', 'G'] : ['A', 'B', 'C'];
  }
  if (u === 'ABG' || u === 'ABCG' || u === 'BCG' || u === 'CAG' || u === 'ACG') {
    /* fall through */
  }
  const out: ('A' | 'B' | 'C' | 'G')[] = [];
  if (u.includes('A')) out.push('A');
  if (u.includes('B')) out.push('B');
  if (u.includes('C')) out.push('C');
  if (u.includes('G') || u.includes('N') || /E$/.test(u) || /\bEF\b/.test(raw)) out.push('G');
  return out;
}

function PhaseTicks({ x, y, phases }: { x: number; y: number; phases: ('A' | 'B' | 'C' | 'G')[] }) {
  if (!phases.length) return null;
  return (
    <g>
      {phases.map((p, i) => (
        <text key={p} x={x + i * 12} y={y} className={styles.phaseTick}>
          {p}
        </text>
      ))}
    </g>
  );
}

function SchemeLineDistance(props: {
  showKm: boolean;
  pct: number | null;
  markerLabel: string;
  phases: ('A' | 'B' | 'C' | 'G')[];
}) {
  const { showKm, pct, markerLabel, phases } = props;
  const fx = pct != null ? 40 + (pct / 100) * 560 : 280;
  return (
    <>
      <line x1="40" y1="60" x2="600" y2="60" className={styles.bus} />
      <rect x="30" y="40" width="28" height="40" className={styles.busbar} />
      <rect x="582" y="40" width="28" height="40" className={styles.busbar} />
      <text x="44" y="28" className={styles.t}>
        Local
      </text>
      <text x="560" y="28" className={styles.t}>
        Remote
      </text>
      <rect x="120" y="48" width="36" height="24" rx="2" className={styles.breaker} />
      <text x="126" y="92" className={styles.t}>
        52
      </text>
      <circle cx="200" cy="60" r="10" className={styles.ct} />
      <text x="190" y="92" className={styles.t}>
        CT
      </text>
      <rect x="240" y="36" width="70" height="48" rx="3" className={styles.relay} />
      <text x="252" y="64" className={styles.tBold}>
        IED
      </text>
      {pct != null && (
        <>
          <circle cx={fx} cy="60" r="8" className={styles.fault} />
          <text x={Math.min(480, Math.max(40, fx - 20))} y="20" className={styles.faultLabel}>
            {markerLabel}
          </text>
          <PhaseTicks x={fx - 10} y={108} phases={phases} />
          {showKm ? (
            <text x={fx - 8} y={78} className={styles.t}>
              km
            </text>
          ) : null}
        </>
      )}
    </>
  );
}

function SchemeTransformerDiff(props: {
  markerLabel: string;
  phases: ('A' | 'B' | 'C' | 'G')[];
}) {
  const { markerLabel, phases } = props;
  return (
    <>
      <rect x="30" y="36" width="22" height="48" className={styles.busbar} />
      <text x="28" y="28" className={styles.t}>
        HV
      </text>
      <line x1="52" y1="60" x2="160" y2="60" className={styles.bus} />
      <circle cx="120" cy="60" r="10" className={styles.ct} />
      <text x="108" y="92" className={styles.t}>
        CT
      </text>
      {/* Transformer: two overlapping windings */}
      <circle cx="230" cy="60" r="28" className={styles.xfmr} />
      <circle cx="258" cy="60" r="28" className={styles.xfmr} />
      <text x="228" y="64" className={styles.tBold}>
        T
      </text>
      <line x1="286" y1="60" x2="400" y2="60" className={styles.bus} />
      <circle cx="340" cy="60" r="10" className={styles.ct} />
      <text x="328" y="92" className={styles.t}>
        CT
      </text>
      <rect x="400" y="36" width="22" height="48" className={styles.busbar} />
      <text x="398" y="28" className={styles.t}>
        LV
      </text>
      <rect x="480" y="36" width="70" height="48" rx="3" className={styles.relay} />
      <text x="492" y="64" className={styles.tBold}>
        IED
      </text>
      <line x1="244" y1="32" x2="244" y2="18" className={styles.zone} />
      <circle cx="244" cy="60" r="8" className={styles.fault} />
      <text x="160" y="18" className={styles.faultLabel}>
        {markerLabel}
      </text>
      <PhaseTicks x={220} y={108} phases={phases} />
      <text x={470} y={100} className={styles.t}>
        87 zone
      </text>
    </>
  );
}

function SchemeBusDiff(props: { markerLabel: string; phases: ('A' | 'B' | 'C' | 'G')[] }) {
  const { markerLabel, phases } = props;
  return (
    <>
      <rect x="80" y="48" width="480" height="18" rx="2" className={styles.busbarWide} />
      <text x="300" y="40" className={styles.tBold}>
        BUS
      </text>
      {[140, 260, 380, 500].map((x, i) => (
        <g key={x}>
          <line x1={x} y1="66" x2={x} y2="95" className={styles.bus} />
          <circle cx={x} cy="100" r="8" className={styles.ct} />
          <text x={x - 10} y="118" className={styles.t}>
            F{i + 1}
          </text>
        </g>
      ))}
      <rect x="560" y="30" width="60" height="40" rx="3" className={styles.relay} />
      <text x="570" y="54" className={styles.tBold}>
        IED
      </text>
      <circle cx="320" cy="57" r="8" className={styles.fault} />
      <text x="200" y="22" className={styles.faultLabel}>
        {markerLabel}
      </text>
      <PhaseTicks x={300} y={18} phases={phases} />
    </>
  );
}

function SchemeGeneratorDiff(props: {
  markerLabel: string;
  phases: ('A' | 'B' | 'C' | 'G')[];
}) {
  const { markerLabel, phases } = props;
  return (
    <>
      <circle cx="100" cy="60" r="32" className={styles.xfmr} />
      <text x="88" y="64" className={styles.tBold}>
        G
      </text>
      <line x1="132" y1="60" x2="280" y2="60" className={styles.bus} />
      <circle cx="180" cy="60" r="10" className={styles.ct} />
      <text x="168" y="92" className={styles.t}>
        CT
      </text>
      <circle cx="240" cy="60" r="10" className={styles.ct} />
      <text x="228" y="92" className={styles.t}>
        CT
      </text>
      <rect x="300" y="36" width="70" height="48" rx="3" className={styles.relay} />
      <text x="312" y="64" className={styles.tBold}>
        IED
      </text>
      <rect x="420" y="40" width="28" height="40" className={styles.busbar} />
      <text x="416" y="28" className={styles.t}>
        Bus
      </text>
      <circle cx="210" cy="60" r="8" className={styles.fault} />
      <text x="150" y="20" className={styles.faultLabel}>
        {markerLabel}
      </text>
      <PhaseTicks x={190} y={108} phases={phases} />
    </>
  );
}

function SchemeLineDiff(props: { markerLabel: string; phases: ('A' | 'B' | 'C' | 'G')[] }) {
  const { markerLabel, phases } = props;
  return (
    <>
      <rect x="30" y="40" width="28" height="40" className={styles.busbar} />
      <text x="28" y="28" className={styles.t}>
        End A
      </text>
      <line x1="58" y1="60" x2="580" y2="60" className={styles.bus} />
      <circle cx="120" cy="60" r="10" className={styles.ct} />
      <rect x="150" y="40" width="50" height="40" rx="3" className={styles.relay} />
      <text x="158" y="64" className={styles.tBold}>
        IED
      </text>
      <rect x="280" y="50" width="80" height="20" rx="2" className={styles.zoneBand} />
      <text x="292" y="64" className={styles.t}>
        87L zone
      </text>
      <circle cx="320" cy="60" r="8" className={styles.fault} />
      <rect x="440" y="40" width="50" height="40" rx="3" className={styles.relay} />
      <text x="448" y="64" className={styles.tBold}>
        IED
      </text>
      <circle cx="520" cy="60" r="10" className={styles.ct} />
      <rect x="582" y="40" width="28" height="40" className={styles.busbar} />
      <text x="560" y="28" className={styles.t}>
        End B
      </text>
      <text x="240" y="20" className={styles.faultLabel}>
        {markerLabel}
      </text>
      <PhaseTicks x={300} y={108} phases={phases} />
    </>
  );
}

function SchemeFeederOc(props: {
  markerLabel: string;
  phases: ('A' | 'B' | 'C' | 'G')[];
  showMarker: boolean;
  /** When true, annotate failed breaker / LBB path (cascade initiator view). */
  breakerFailure?: boolean;
}) {
  const { markerLabel, phases, showMarker, breakerFailure } = props;
  return (
    <>
      <rect x="30" y="40" width="28" height="40" className={styles.busbar} />
      <text x="28" y="28" className={styles.t}>
        Bus
      </text>
      <line x1="58" y1="60" x2="520" y2="60" className={styles.bus} />
      <rect x="120" y="48" width="36" height="24" rx="2" className={styles.breaker} />
      <text x="126" y="92" className={styles.t}>
        52{breakerFailure ? ' (BF)' : ''}
      </text>
      <circle cx="200" cy="60" r="10" className={styles.ct} />
      <text x="190" y="92" className={styles.t}>
        CT
      </text>
      <rect x="260" y="36" width="70" height="48" rx="3" className={styles.relay} />
      <text x="272" y="64" className={styles.tBold}>
        IED
      </text>
      <line x1="520" y1="60" x2="520" y2="95" className={styles.bus} />
      <text x="500" y="112" className={styles.t}>
        Load
      </text>
      {showMarker && (
        <>
          <circle cx="400" cy="60" r="8" className={styles.fault} />
          <text x="320" y="20" className={styles.faultLabel}>
            {markerLabel}
          </text>
          <PhaseTicks x={380} y={108} phases={phases} />
        </>
      )}
    </>
  );
}

/** Cascade / LBB: initiator feeder fault + upstream backup clearance. */
function SchemeCascadeLbb(props: {
  markerLabel: string;
  phases: ('A' | 'B' | 'C' | 'G')[];
  leftLabel: string;
  rightLabel: string;
}) {
  const { markerLabel, phases, leftLabel, rightLabel } = props;
  return (
    <>
      <rect x="20" y="36" width="18" height="40" className={styles.busbar} />
      <text x="14" y="26" className={styles.t}>
        LV bus
      </text>
      <line x1="38" y1="56" x2="210" y2="56" className={styles.bus} />
      <rect x="70" y="44" width="28" height="24" rx="2" className={styles.breaker} />
      <text x="68" y="88" className={styles.t}>
        52 fail
      </text>
      <circle cx="130" cy="56" r="8" className={styles.ct} />
      <rect x="155" y="36" width="50" height="40" rx="3" className={styles.relay} />
      <text x="160" y="60" className={styles.tBold}>
        LV
      </text>
      <circle cx="200" cy="56" r="7" className={styles.fault} />
      <text x="40" y="112" className={styles.t}>
        {leftLabel.slice(0, 18)}
      </text>

      <line x1="220" y1="56" x2="300" y2="56" className={styles.zone} />
      <text x="230" y="48" className={styles.t}>
        intertrip
      </text>

      <rect x="300" y="36" width="18" height="40" className={styles.busbar} />
      <text x="292" y="26" className={styles.t}>
        HV
      </text>
      <line x1="318" y1="56" x2="520" y2="56" className={styles.bus} />
      <rect x="350" y="44" width="28" height="24" rx="2" className={styles.breaker} />
      <text x="350" y="88" className={styles.t}>
        52
      </text>
      <circle cx="410" cy="56" r="8" className={styles.ct} />
      <rect x="440" y="36" width="50" height="40" rx="3" className={styles.relay} />
      <text x="445" y="60" className={styles.tBold}>
        HV
      </text>
      <text x="360" y="112" className={styles.t}>
        {rightLabel.slice(0, 18)}
      </text>

      <text x="180" y="18" className={styles.faultLabel}>
        {markerLabel}
      </text>
      <PhaseTicks x={185} y={108} phases={phases} />
    </>
  );
}

export function OneLineBay({
  substation,
  bay,
  relay,
  feeder,
  faultType,
  distanceKm,
  lineLengthKm,
  distanceApplicable,
  schemeHint,
  onOpenDr,
  cascadeEnds,
}: Props) {
  const kind = inferBaySchemeKind({
    bay,
    relay,
    feeder,
    schemeHint,
    distanceApplicable,
  });
  const phases = faultPhases(faultType);
  const hintU = `${schemeHint || ''}`.toUpperCase();
  const isBreakerFailure =
    /\b50BF\b|\b62BF\b|\bLBB\b/.test(hintU) || cascadeEnds?.mode === 'cascade';
  const useCascadeSchematic = cascadeEnds?.mode === 'cascade';

  const showKm =
    kind === 'line_distance' &&
    distanceApplicable === true &&
    distanceKm != null &&
    Number.isFinite(distanceKm);

  const pct = showKm
    ? lineLengthKm != null && lineLengthKm > 0
      ? Math.max(4, Math.min(96, (distanceKm! / lineLengthKm) * 100))
      : 35
    : kind === 'line_distance' && faultType
      ? 35
      : null;

  const markerLabel = (() => {
    const parts: string[] = [];
    const hint = `${schemeHint || ''} ${bay || ''}`.toUpperCase();
    const hasTrip = /\bTRIP\b/.test(hint);
    const hasPickup = /\bPICKUP\b/.test(hint);
    const assertSuffix =
      hasTrip && hasPickup
        ? ' pickup with trip'
        : hasTrip
          ? ' trip'
          : hasPickup
            ? ' pickup'
            : '';
    const codes = extractOperatedCodes(schemeHint);

    if (kind === 'bus_diff') parts.push(`87B${assertSuffix}`.trim());
    else if (kind === 'transformer_diff') {
      // On PTR / 7UT, 87G in the DR is REF / ground-diff — not generator 87G
      let el = '87T';
      if (/\b87G\b/.test(hint) && /\b87T\b/.test(hint)) el = '87T/87G(REF)';
      else if (/\b87G\b/.test(hint) && !/\b87T\b/.test(hint)) el = '87G(REF)';
      parts.push(`${el}${assertSuffix}`.trim());
    } else if (kind === 'line_diff') parts.push(`87L${assertSuffix}`.trim());
    else if (kind === 'generator_diff') parts.push(`87G${assertSuffix}`.trim());
    else if (/\b87/.test(hint)) parts.push(`87${assertSuffix}`.trim());
    else if (codes.length) {
      parts.push(
        `${codes.map((c) => formatAnsiCompact(c)).join('/')} ${assertSuffix.trim()}`.trim(),
      );
    } else if (assertSuffix) {
      parts.push(assertSuffix.trim());
    }
    if (faultType) parts.push(faultType);
    if (showKm) parts.push(`~${distanceKm!.toFixed(1)} km`);
    else if (kind !== 'line_distance' && kind !== 'feeder_oc' && !useCascadeSchematic) {
      parts.push('zone (no km)');
    }
    return parts.join(' · ') || 'FAULT';
  })();

  const schemeTitle: Record<BaySchemeKind, string> = {
    line_distance: 'Line / distance',
    line_diff: 'Line differential',
    transformer_diff: 'Transformer differential',
    bus_diff: 'Bus differential',
    generator_diff: 'Generator differential',
    feeder_oc: 'Feeder / overcurrent',
  };

  const hintText = cascadeEnds
    ? cascadeEnds.mode === 'cascade'
      ? `Cascade context — ${cascadeEnds.leftRole} (${cascadeEnds.leftLabel}) fails to clear; ${cascadeEnds.rightRole} (${cascadeEnds.rightLabel}) provides backup clearance. Schematic shows initiator bay template.`
      : `Multi-end context — ${cascadeEnds.leftRole} ↔ ${cascadeEnds.rightRole}. Schematic shows local-end template.`
    : kind === 'line_distance'
      ? 'Schematic context only — not a verified network model. Km marker only when distance location applies.'
      : `Schematic context only — ${schemeTitle[kind]} template: zone marker, no invented fault km.`;

  const schemeTag = cascadeEnds
    ? cascadeEnds.mode === 'cascade'
      ? 'Cascade / LBB'
      : 'Local / Remote'
    : schemeTitle[kind];

  return (
    <div className={`panel ${styles.wrap}`}>
      <div className="panel-header">
        {cascadeEnds ? 'Combined one-line (context)' : 'Bay one-line (context)'}
        <span className={styles.schemeTag}>{schemeTag}</span>
        {onOpenDr ? (
          <button type="button" className="btn btn-sm" onClick={onOpenDr} style={{ float: 'right' }}>
            Open at fault → DR
          </button>
        ) : null}
      </div>
      <div
        className={`panel-body ${styles.body}`}
        role={onOpenDr ? 'button' : undefined}
        tabIndex={onOpenDr ? 0 : undefined}
        onClick={onOpenDr}
        onKeyDown={
          onOpenDr
            ? (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  onOpenDr();
                }
              }
            : undefined
        }
        style={onOpenDr ? { cursor: 'pointer' } : undefined}
        title={onOpenDr ? 'Click to open DR workspace' : undefined}
      >
        <div className={styles.labels}>
          <span>{substation || 'Substation'}</span>
          <span className="mono">{bay || 'Bay'}</span>
          <span className="mono">{relay || 'Relay'}</span>
          {feeder ? <span>{feeder}</span> : null}
        </div>
        {cascadeEnds ? (
          <div className={styles.labels} style={{ marginTop: 4, opacity: 0.92 }}>
            <span className="mono">
              {cascadeEnds.leftRole}: {cascadeEnds.leftLabel}
            </span>
            <span aria-hidden>{cascadeEnds.mode === 'cascade' ? '→' : '↔'}</span>
            <span className="mono">
              {cascadeEnds.rightRole}: {cascadeEnds.rightLabel}
            </span>
          </div>
        ) : null}
        <svg
          viewBox={kind === 'bus_diff' || useCascadeSchematic ? '0 0 640 130' : '0 0 640 120'}
          className={styles.svg}
          aria-label={
            useCascadeSchematic
              ? 'Cascade / LBB combined one-line'
              : `${schemeTitle[kind]} bay one-line`
          }
        >
          {useCascadeSchematic ? (
            <SchemeCascadeLbb
              markerLabel={markerLabel}
              phases={phases}
              leftLabel={cascadeEnds?.leftLabel || 'Initiator'}
              rightLabel={cascadeEnds?.rightLabel || 'Backup'}
            />
          ) : (
            <>
              {kind === 'line_distance' && (
                <SchemeLineDistance
                  showKm={showKm}
                  pct={pct}
                  markerLabel={markerLabel}
                  phases={phases}
                />
              )}
              {kind === 'line_diff' && (
                <SchemeLineDiff markerLabel={markerLabel} phases={phases} />
              )}
              {kind === 'transformer_diff' && (
                <SchemeTransformerDiff markerLabel={markerLabel} phases={phases} />
              )}
              {kind === 'bus_diff' && (
                <SchemeBusDiff markerLabel={markerLabel} phases={phases} />
              )}
              {kind === 'generator_diff' && (
                <SchemeGeneratorDiff markerLabel={markerLabel} phases={phases} />
              )}
              {kind === 'feeder_oc' && (
                <SchemeFeederOc
                  markerLabel={markerLabel}
                  phases={phases}
                  showMarker={Boolean(faultType) || extractOperatedCodes(schemeHint).length > 0}
                  breakerFailure={isBreakerFailure}
                />
              )}
            </>
          )}
        </svg>
        <p className={styles.hint}>{hintText}</p>
      </div>
    </div>
  );
}
