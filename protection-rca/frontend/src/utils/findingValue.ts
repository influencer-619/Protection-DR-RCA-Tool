/** Format consistency expected/observed cells for engineers (not raw JSON). */

const STEP_LABEL: Record<string, string> = {
  protection_pickup: 'Pickup',
  pickup: 'Pickup',
  protection_trip: 'Trip',
  trip: 'Trip',
  breaker_trip_command: 'Trip command',
  '52a_change': 'Breaker (52a)',
  breaker: 'Breaker',
  current_interruption: 'Interrupt',
  interrupt: 'Interrupt',
  interruption: 'Interrupt',
};

const KEY_LABEL: Record<string, string> = {
  ...STEP_LABEL,
  enabled: 'Enabled',
  pickup: 'Pickup',
  trip: 'Trip',
  order: 'Order',
  present: 'Present',
  times_s: 'Times',
  steps: 'Steps',
  value: '',
};

function unwrap(raw: unknown): unknown {
  if (raw == null) return raw;
  if (typeof raw === 'object' && !Array.isArray(raw)) {
    const obj = raw as Record<string, unknown>;
    const keys = Object.keys(obj);
    if (keys.length === 1 && keys[0] === 'value') return unwrap(obj.value);
  }
  if (typeof raw === 'string') {
    const t = raw.trim();
    if (
      (t.startsWith('{') && t.endsWith('}')) ||
      (t.startsWith('[') && t.endsWith(']'))
    ) {
      try {
        const json = t
          .replace(/\bNone\b/g, 'null')
          .replace(/\bTrue\b/g, 'true')
          .replace(/\bFalse\b/g, 'false')
          .replace(/'/g, '"');
        return unwrap(JSON.parse(json));
      } catch {
        return raw;
      }
    }
  }
  return raw;
}

function labelKey(key: string): string {
  if (KEY_LABEL[key]) return KEY_LABEL[key];
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function fmtBool(v: string): string {
  const u = v.toUpperCase();
  if (u === 'TRUE' || u === 'YES') return 'yes';
  if (u === 'FALSE' || u === 'NO') return 'no';
  if (u === 'NONE' || u === 'NULL') return '—';
  return v;
}

function fmtTime(n: number): string {
  if (!Number.isFinite(n)) return '—';
  const abs = Math.abs(n);
  if (abs >= 1000) return `${n.toFixed(0)} µs`;
  if (abs >= 2) return `${n.toFixed(2)} s`;
  return `${n.toFixed(3)} s`;
}

function isTimeMap(obj: Record<string, unknown>): boolean {
  const keys = Object.keys(obj);
  if (keys.length === 0) return false;
  return keys.every(
    (k) =>
      k in STEP_LABEL ||
      ['protection_pickup', 'protection_trip', 'breaker_trip_command', '52a_change', 'current_interruption'].includes(
        k,
      ),
  );
}

function formatSequenceMap(obj: Record<string, unknown>): string {
  const order = [
    'protection_pickup',
    'protection_trip',
    'breaker_trip_command',
    '52a_change',
    'current_interruption',
  ];
  const keys = [...order.filter((k) => k in obj), ...Object.keys(obj).filter((k) => !order.includes(k))];
  return keys
    .map((k) => {
      const n = Number(obj[k]);
      return `${STEP_LABEL[k] ?? labelKey(k)} ${fmtTime(n)}`;
    })
    .join('  →  ');
}

function formatKvPairs(s: string): string {
  if (!s.includes('=')) return s.replace(/^monotonic\s+/i, '');
  return s
    .split(',')
    .map((part) => {
      const idx = part.indexOf('=');
      if (idx < 0) return part.trim();
      const k = part.slice(0, idx).trim();
      const val = part.slice(idx + 1).trim();
      const name = labelKey(k) || k;
      return `${name}: ${fmtBool(val)}`;
    })
    .join(' · ');
}

function formatObject(obj: Record<string, unknown>): string {
  if ('order' in obj && (typeof obj.order === 'string' || Array.isArray(obj.order))) {
    if (typeof obj.order === 'string') return obj.order.replace(/^monotonic\s+/i, '');
    return (obj.order as unknown[]).map((x) => STEP_LABEL[String(x)] ?? labelKey(String(x))).join(' → ');
  }
  if ('times_s' in obj && obj.times_s && typeof obj.times_s === 'object') {
    return formatSequenceMap(obj.times_s as Record<string, unknown>);
  }
  if ('present' in obj && Array.isArray(obj.present)) {
    const names = obj.present.map((x) => STEP_LABEL[String(x)] ?? labelKey(String(x)));
    return names.length ? `Only ${names.join(', ')} present` : 'No sequence events';
  }
  if (isTimeMap(obj)) return formatSequenceMap(obj);
  return Object.entries(obj)
    .filter(([k]) => k !== 'steps')
    .map(([k, val]) => {
      const name = labelKey(k);
      if (val == null) return name ? `${name}: —` : '—';
      if (typeof val === 'object') return formatFindingValue(val);
      if (typeof val === 'boolean') return `${name}: ${val ? 'yes' : 'no'}`;
      if (typeof val === 'number') {
        if (k.endsWith('_s') || k.includes('time')) return `${name}: ${fmtTime(val)}`;
        return `${name}: ${Number.isInteger(val) ? String(val) : val.toFixed(3)}`;
      }
      return name ? `${name}: ${fmtBool(String(val))}` : String(val);
    })
    .filter(Boolean)
    .join(' · ');
}

export function formatFindingValue(raw: unknown): string {
  const v = unwrap(raw);
  if (v == null || v === '') return '—';
  if (typeof v === 'number') return Number.isFinite(v) ? String(v) : '—';
  if (typeof v === 'boolean') return v ? 'yes' : 'no';
  if (Array.isArray(v)) {
    return v.map((x) => STEP_LABEL[String(x)] ?? String(x)).join(' → ') || '—';
  }
  if (typeof v === 'object') return formatObject(v as Record<string, unknown>) || '—';
  const s = String(v).trim();
  if (/^events present:/i.test(s)) {
    const inner = s.replace(/^events present:\s*/i, '');
    const parsed = unwrap(inner);
    if (Array.isArray(parsed)) {
      const names = parsed.map((x) => STEP_LABEL[String(x)] ?? String(x));
      return names.length ? `Only ${names.join(', ')} present` : 'No sequence events';
    }
  }
  if (s.startsWith('{') || s.startsWith('[')) return s;
  if (s.includes('=')) return formatKvPairs(s);
  return s
    .replace(/^monotonic\s+/i, '')
    .replace(/\s*->\s*/g, ' → ')
    .replace(/\s+/g, ' ')
    .trim();
}

export function formatCheckName(checkType: string): string {
  const names: Record<string, string> = {
    protection_sequence: 'Protection sequence',
    enabled_vs_pickup: 'Enabled vs pickup',
    enabled_vs_trip: 'Enabled vs trip',
    pickup_vs_trip: 'Pickup vs trip',
  };
  if (names[checkType]) return names[checkType];
  return checkType.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
