/**
 * App timestamps (created_at): UTC. Naive ISO without Z is treated as UTC.
 * DR / event_datetime: COMTRADE wall clock — never shift by attaching Z.
 */

const HAS_TZ = /(?:[zZ]|[+-]\d{2}:?\d{2})$/;

function normalizeIsoNaive(raw: string): string {
  let s = raw.trim();
  s = s.includes('T') ? s : s.replace(' ', 'T');
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) s = `${s}T00:00:00`;
  return s;
}

/** Server / upload time (UTC → browser local). */
export function parseApiDate(raw: string | null | undefined): Date | null {
  if (raw == null) return null;
  let s = String(raw).trim();
  if (!s) return null;

  if (!HAS_TZ.test(s)) {
    s = normalizeIsoNaive(s);
    if (!HAS_TZ.test(s)) s = `${s}Z`;
  }

  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

/**
 * COMTRADE disturbance time — use the clock printed on the DR.
 * Strip any Z/+offset so 20:12 stays 20:12 (not shifted to IST from false UTC).
 */
export function parseDrDate(raw: string | null | undefined): Date | null {
  if (raw == null) return null;
  let s = String(raw).trim();
  if (!s) return null;

  // Drop TZ so Date parses as local wall clock matching CFG digits
  s = s.replace(/[zZ]$/, '').replace(/[+-]\d{2}:?\d{2}$/, '');
  s = normalizeIsoNaive(s);

  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** App UTC timestamps (Created, …) shown in IST with an IST label (not GMT+5:30). */
export function formatApiDateLocal(
  raw: string | null | undefined,
  fallback = '—',
): string {
  const d = parseApiDate(raw);
  if (!d) return fallback;

  const parts = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).formatToParts(d);

  const get = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((p) => p.type === type)?.value ?? '';

  return `${get('day')}/${get('month')}/${get('year')}, ${get('hour')}:${get('minute')}:${get('second')} IST`;
}

/** DR time as on the COMTRADE / relay stamp (no UTC conversion). */
export function formatDrDate(
  raw: string | null | undefined,
  fallback = '—',
): string {
  if (raw == null || !String(raw).trim()) return fallback;
  const s = String(raw).trim();
  const m = s.match(
    /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?/,
  );
  if (m) {
    const [, y, mo, d, h, mi, sec] = m;
    return `${d}/${mo}/${y}, ${h}:${mi}:${sec}`;
  }
  const d = parseDrDate(s);
  if (!d) return fallback;
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}
