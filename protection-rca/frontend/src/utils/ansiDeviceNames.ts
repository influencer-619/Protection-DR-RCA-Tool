/** ANSI / IEEE C37.2 device numbers → technical names for the web UI. */

const ANSI_TECHNICAL_NAMES: Record<string, string> = {
  '21': 'Distance protection',
  '21P': 'Phase distance',
  '21G': 'Ground distance',
  '21N': 'Ground distance',
  '25': 'Synchronism check',
  '27': 'Undervoltage',
  '32': 'Directional power',
  '32R': 'Reverse power',
  '46': 'Negative-sequence overcurrent',
  '47': 'Phase-sequence voltage',
  '48': 'Incomplete sequence / stalled rotor',
  '49': 'Thermal overload',
  '50': 'Instantaneous overcurrent',
  '50P': 'Phase instantaneous overcurrent',
  '50N': 'Neutral / earth instantaneous overcurrent',
  '50G': 'Ground instantaneous overcurrent',
  '50BF': 'Breaker failure',
  '50NBF': 'Neutral breaker failure',
  '51': 'Time overcurrent',
  '51P': 'Phase time overcurrent',
  '51N': 'Neutral / earth time overcurrent',
  '51G': 'Ground time overcurrent',
  '59': 'Overvoltage',
  '67': 'Directional overcurrent',
  '67P': 'Phase directional overcurrent',
  '67N': 'Neutral / earth directional overcurrent',
  '67G': 'Ground directional overcurrent',
  '68': 'Power-swing block',
  '78': 'Out-of-step / loss of synchronism',
  '79': 'Autoreclose',
  '81': 'Frequency',
  '81U': 'Underfrequency',
  '81O': 'Overfrequency',
  '81R': 'Rate of change of frequency (ROCOF)',
  '86': 'Lockout / master trip',
  '87': 'Differential',
  '87B': 'Bus differential',
  '87L': 'Line differential',
  '87T': 'Transformer differential',
  '87G': 'Generator differential',
  '87GT': 'Generator-transformer differential',
  '87RGF': 'Restricted earth-fault (REF)',
  '62BF': 'Breaker-failure timer',
  LBB: 'Local breaker backup',
};

export function normalizeAnsiCode(code: string | null | undefined): string {
  const raw = String(code || '')
    .trim()
    .toUpperCase();
  if (!raw || raw === 'UNKNOWN' || raw === 'GENERAL' || raw === '—' || raw === '-') {
    return '';
  }
  return raw;
}

export function ansiTechnicalName(code: string | null | undefined): string | null {
  const c = normalizeAnsiCode(code);
  if (!c) return null;
  if (ANSI_TECHNICAL_NAMES[c]) return ANSI_TECHNICAL_NAMES[c];
  const m = c.match(/^([0-9]+[A-Z]*?)(\d+)$/);
  if (m && ANSI_TECHNICAL_NAMES[m[1]]) return ANSI_TECHNICAL_NAMES[m[1]];
  return null;
}

/** Strip any existing ``(technical name)`` so we can re-format cleanly. */
function stripAnsiParenName(part: string): string {
  return String(part || '')
    .replace(/\s*\([^)]*\)\s*/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function extractAnsiToken(part: string): string {
  const clean = stripAnsiParenName(part);
  const m = clean.match(/^([0-9A-Za-z]+)/);
  return m ? m[1] : clean;
}

/** `50BF (Breaker failure)` — for detail pages / tooltips. */
export function formatAnsi(code: string | null | undefined): string {
  const c = normalizeAnsiCode(extractAnsiToken(String(code || ''))) || String(code || '').trim();
  if (!c) return '—';
  const name = ansiTechnicalName(c);
  return name ? `${c} (${name})` : c;
}

/** Compact code only — `50BF` — for dense tables / badges. */
export function formatAnsiCompact(code: string | null | undefined): string {
  const c = normalizeAnsiCode(extractAnsiToken(String(code || ''))) || String(code || '').trim();
  return c || '—';
}

/** Parse a protection_summary string into ANSI tokens. */
export function parseAnsiSummaryParts(summary: string | null | undefined): string[] {
  if (!summary) return [];
  return String(summary)
    .split(/[,;/|]+/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => {
      const m = stripAnsiParenName(p).match(
        /^([0-9A-Za-z]+)\s+(trip|pickup|operate|start)\b/i,
      );
      if (m) return m[1];
      return extractAnsiToken(p);
    })
    .filter(Boolean);
}

/** Dense table cell: `50BF · 50P · 51P` with full names available via title. */
export function formatAnsiSummaryCompact(summary: string | null | undefined): string {
  const codes = parseAnsiSummaryParts(summary);
  if (!codes.length) return summary ? String(summary) : '—';
  return codes.map((c) => formatAnsiCompact(c)).join(' · ');
}

/** Full named list for tooltips / detail views. */
export function formatAnsiSummary(summary: string | null | undefined): string {
  const codes = parseAnsiSummaryParts(summary);
  if (!codes.length) return summary ? String(summary) : '—';
  return codes.map((c) => formatAnsi(c)).join('; ');
}

export const ANSI_CODE_OPTIONS = Object.keys(ANSI_TECHNICAL_NAMES).sort((a, b) =>
  a.localeCompare(b, undefined, { numeric: true }),
);
