/** Primary vs secondary quantity side for COMTRADE / electrical views. */

export type QuantitySideMode = 'secondary' | 'primary' | 'both';
export type QuantitySide = 'primary' | 'secondary' | 'unknown';

export function classifyChannelSide(
  name: string,
  units?: string | null,
  ps?: string | null,
): QuantitySide {
  const n = String(name || '')
    .toUpperCase()
    .replace(/\s+/g, '')
    .replace(/-/g, '_');
  const u = String(units || '')
    .toUpperCase()
    .replace(/\s+/g, '');
  const p = String(ps || '')
    .toUpperCase()
    .trim();

  if (p === 'P' || p === 'PRIMARY') return 'primary';
  if (p === 'S' || p === 'SECONDARY') return 'secondary';

  if (
    /_PRI(?:MARY)?(?:_|$)/.test(n) ||
    n.endsWith('PRI') ||
    n.includes('PRIMARY') ||
    n.includes('_P_') ||
    /\bPRI\b/.test(n.replace(/_/g, ' '))
  ) {
    return 'primary';
  }
  if (
    /_SEC(?:ONDARY)?(?:_|$)/.test(n) ||
    n.endsWith('SEC') ||
    n.includes('SECONDARY')
  ) {
    return 'secondary';
  }

  // Unit heuristics (common dual-channel COMTRADE packs)
  if (u === 'KA' || u === 'KV' || u === 'KA.' || u === 'KV.') return 'primary';
  if (
    u === 'A' ||
    u === 'AMP' ||
    u === 'AMPS' ||
    u === 'V' ||
    u === 'VOLT' ||
    u === 'VOLTS'
  ) {
    return 'secondary';
  }

  return 'unknown';
}

export function detectAvailableSides(
  items: Array<{ name: string; units?: string | null; ps?: string | null; channel_type?: string }>,
): { hasPrimary: boolean; hasSecondary: boolean } {
  let hasPrimary = false;
  let hasSecondary = false;
  for (const it of items) {
    if (String(it.channel_type || '').toUpperCase() === 'DIGITAL') continue;
    const side = classifyChannelSide(it.name, it.units, it.ps);
    if (side === 'primary') hasPrimary = true;
    if (side === 'secondary') hasSecondary = true;
  }
  return { hasPrimary, hasSecondary };
}

export function filterByQuantitySide<
  T extends {
    name?: string;
    units?: string | null;
    unit?: string | null;
    ps?: string | null;
    channel_type?: string;
  },
>(items: T[], mode: QuantitySideMode): T[] {
  if (mode === 'both') return items;
  return items.filter((it) => {
    if (String(it.channel_type || '').toUpperCase() === 'DIGITAL') return true;
    const name = it.name || '';
    const units = it.units ?? it.unit ?? null;
    const side = classifyChannelSide(name, units, it.ps);
    if (side === 'unknown') return true;
    return side === mode;
  });
}

export function filterWaveformChannelsBySide<
  T extends {
    channel: {
      name: string;
      units?: string | null;
      ps?: string | null;
      channel_type: string;
    };
  },
>(channels: T[], mode: QuantitySideMode): T[] {
  if (mode === 'both') return channels;
  return channels.filter((c) => {
    if (c.channel.channel_type === 'DIGITAL') return true;
    const side = classifyChannelSide(c.channel.name, c.channel.units, c.channel.ps);
    if (side === 'unknown') return true;
    return side === mode;
  });
}

export function filterMeasurementsBySide<
  T extends { quantity: string; unit?: string | null },
>(meas: T[], mode: QuantitySideMode): T[] {
  if (mode === 'both') return meas;
  return meas.filter((m) => {
    const base = m.quantity.replace(/_(rms|phasor|peak)$/i, '');
    // Sequence / Z / freq are analysis products — keep on secondary (analysis default)
    if (/^(I[012]|V[012]|freq|Z_|R_)/i.test(m.quantity) || /^Z_/i.test(m.quantity)) {
      return mode === 'secondary';
    }
    const side = classifyChannelSide(base, m.unit);
    if (side === 'unknown') {
      // Unit-only: kA/kV → primary
      const u = String(m.unit || '').toUpperCase();
      if (u === 'KA' || u === 'KV') return mode === 'primary';
      if (u === 'A' || u === 'V') return mode === 'secondary';
      return mode === 'secondary';
    }
    return side === mode;
  });
}

export function sideLabel(mode: QuantitySideMode): string {
  if (mode === 'primary') return 'Primary (kA / kV)';
  if (mode === 'secondary') return 'Secondary (A / V)';
  return 'Both (primary + secondary)';
}
