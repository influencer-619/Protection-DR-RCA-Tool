import styles from './OneLineBay.module.css';

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
  /** Optional protection hint e.g. 87B */
  schemeHint?: string | null;
  /** Navigate to DR / waveforms when bay schematic is activated. */
  onOpenDr?: () => void;
}

function looksDifferential(opts: {
  bay?: string | null;
  relay?: string | null;
  feeder?: string | null;
  schemeHint?: string | null;
}): boolean {
  const blob = `${opts.bay || ''} ${opts.relay || ''} ${opts.feeder || ''} ${opts.schemeHint || ''}`.toUpperCase();
  return (
    /\b87[TBLG]?\b/.test(blob) ||
    /BUS\s*ZONE|BUS\s*DIFF|TRANSFORMER\s*DIFF|LINE\s*DIFF|GENERATOR\s*DIFF|DIFFERENTIAL/.test(
      blob,
    )
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
}: Props) {
  const differential = looksDifferential({ bay, relay, feeder, schemeHint });
  const showKm =
    distanceApplicable === true &&
    !differential &&
    distanceKm != null &&
    Number.isFinite(distanceKm);

  const pct = showKm
    ? lineLengthKm != null && lineLengthKm > 0
      ? Math.max(4, Math.min(96, (distanceKm! / lineLengthKm) * 100))
      : 35
    : faultType || differential
      ? 35
      : null;

  const markerLabel = (() => {
    const parts: string[] = [];
    if (differential) {
      const m = `${schemeHint || ''} ${bay || ''} ${relay || ''}`.toUpperCase();
      if (/\b87B\b|BUS/.test(m)) parts.push('87B');
      else if (/\b87T\b|TRANSFORMER/.test(m)) parts.push('87T');
      else if (/\b87L\b/.test(m)) parts.push('87L');
      else if (/\b87G\b|GENERATOR/.test(m)) parts.push('87G');
      else parts.push('87');
    }
    if (faultType) parts.push(faultType);
    if (showKm) parts.push(`~${distanceKm!.toFixed(1)} km`);
    else if (differential) parts.push('zone (no km)');
    return parts.join(' · ') || 'FAULT';
  })();

  return (
    <div className={`panel ${styles.wrap}`}>
      <div className="panel-header">
        Bay one-line (context)
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
        <svg viewBox="0 0 640 120" className={styles.svg} aria-label="Simple feeder one-line">
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
              <circle cx={40 + (pct / 100) * 560} cy="60" r="8" className={styles.fault} />
              <text
                x={Math.min(480, Math.max(40, 40 + (pct / 100) * 560 - 20))}
                y="20"
                className={styles.faultLabel}
              >
                {markerLabel}
              </text>
            </>
          )}
        </svg>
        <p className={styles.hint}>
          {differential || distanceApplicable === false
            ? 'Schematic context only — differential / non-distance case: no fault km on this diagram.'
            : 'Schematic context only — not a verified network model. Km marker only when distance location applies.'}
        </p>
      </div>
    </div>
  );
}
