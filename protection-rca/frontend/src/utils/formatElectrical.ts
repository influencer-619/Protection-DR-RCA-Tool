/** Format electrical quantities with proper units (A, kV, V, Ω, Hz, km). */

export function normalizeUnit(raw?: string | null, roleHint?: string): string {
  const u = (raw || '').trim();
  const ul = u.toLowerCase().replace(/\s+/g, '');
  const role = (roleHint || '').toUpperCase();

  if (['a', 'amp', 'amps', 'ampere', 'amperes'].includes(ul)) return 'A';
  if (['ka', 'kiloamp', 'kiloamps'].includes(ul)) return 'kA';
  if (['v', 'volt', 'volts'].includes(ul)) return 'V';
  if (['kv', 'kilovolt', 'kilovolts'].includes(ul)) return 'kV';
  if (['ohm', 'ohms', 'ω'].includes(ul) || u === 'Ω') return 'Ω';
  if (['hz', 'hertz'].includes(ul)) return 'Hz';
  if (['km', 'kilometer', 'kilometre'].includes(ul)) return 'km';
  if (['ms', 'millisecond', 'milliseconds'].includes(ul)) return 'ms';
  if (['s', 'sec', 'second', 'seconds'].includes(ul)) return 's';
  if (['deg', 'degree', 'degrees', '°'].includes(ul)) return '°';
  if (ul === 'w' || ul === 'watt' || ul === 'watts') return 'W';
  if (ul === 'pu' || ul === 'p.u.') return 'pu';

  if (role.startsWith('I')) return 'A';
  if (role.startsWith('V')) return 'V';
  if (role.includes('Z') || role.includes('IMP')) return 'Ω';
  if (role.includes('FREQ') || role === 'F') return 'Hz';

  return u;
}

export function inferUnitFromName(name?: string | null, fallback?: string | null): string {
  const n = `${name || ''}`.toUpperCase();
  if (/\bI[ABC0N]?\b|CURRENT|AMP|_RMS/.test(n) && !/VOLT|UL|VA|VB|VC/.test(n)) {
    return normalizeUnit(fallback, 'I') || 'A';
  }
  if (/\bV[ABC0N]?\b|UL[123]|VOLT/.test(n)) {
    return normalizeUnit(fallback, 'V') || 'V';
  }
  if (/^Z_|IMPED|OHM/.test(n)) return 'Ω';
  if (/FREQ|^F$/.test(n)) return 'Hz';
  if (/KM|DISTANCE/.test(n)) return 'km';
  return normalizeUnit(fallback) || '';
}

export function formatNumber(value: number | null | undefined, digits = 3): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const n = Number(value);
  if (Math.abs(n) >= 1000) return n.toFixed(1);
  if (Math.abs(n) >= 100) return n.toFixed(2);
  return n.toFixed(digits);
}

/** Value with unit, e.g. "4.001 A", "12.7 kV", "3.18 Ω". */
export function formatElectrical(
  value: number | null | undefined,
  unit?: string | null,
  opts?: { digits?: number; roleHint?: string; nameHint?: string },
): string {
  if (value == null || Number.isNaN(Number(value))) return '—';
  const u =
    normalizeUnit(unit, opts?.roleHint) ||
    inferUnitFromName(opts?.nameHint, unit) ||
    '';
  const num = formatNumber(value, opts?.digits ?? 3);
  return u ? `${num} ${u}` : num;
}

export function unitLabel(unit?: string | null, roleHint?: string): string {
  return normalizeUnit(unit, roleHint) || '—';
}
