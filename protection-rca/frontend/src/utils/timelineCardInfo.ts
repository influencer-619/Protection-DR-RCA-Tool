/** Engineer-facing labels for sequence-of-operation timeline cards. */

import type { TimelineEntry } from '@/types';
import { formatCheckName } from '@/utils/findingValue';

const HIDDEN_KEYS = new Set([
  'absolute_time',
  'event_type',
  'timestamp',
  'source',
  'confidence',
  'label',
]);

const EVENT_TITLE: Record<string, string> = {
  protection_pickup: 'Protection pickup',
  protection_trip: 'Protection trip',
  breaker_trip_command: 'Trip command',
  '52a_change': 'Breaker 52a status change',
  '52b_change': 'Breaker 52b status change',
  current_increase: 'Current increase',
  current_interruption: 'Current interruption',
  voltage_change: 'Voltage change',
  fault_inception: 'Fault inception',
  reclose: 'Reclose',
  lockout: 'Lockout',
  intertrip: 'Intertrip',
  communication_signal: 'Communication signal',
};

export interface TimelineFact {
  label: string;
  value: string;
}

export interface TimelineCardInfo {
  title: string;
  summary: string;
  facts: TimelineFact[];
  transition: string | null;
}

function normType(raw: string): string {
  return (raw || '').trim().toLowerCase().replace(/[\s-]+/g, '_');
}

export function timelineEventTitle(eventType: string): string {
  const key = normType(eventType);
  if (EVENT_TITLE[key]) return EVENT_TITLE[key];
  return formatCheckName(eventType || 'event');
}

function asRecord(v: unknown): Record<string, unknown> | null {
  if (v && typeof v === 'object' && !Array.isArray(v)) return v as Record<string, unknown>;
  return null;
}

function parseMeta(e: TimelineEntry): Record<string, unknown> {
  // Prefer full analysis payload; description is often truncated JSON from persist.
  const payload = asRecord(e.payload);
  if (payload) {
    const nested = asRecord(payload.metadata) || asRecord(payload.meta);
    return { ...(nested || {}), ...payload };
  }
  const details = asRecord(e.details);
  if (details) {
    const nested = asRecord(details.metadata) || asRecord(details.meta);
    return { ...(nested || {}), ...details };
  }
  const desc = (e.description || '').trim();
  if (!desc) return {};
  if (desc.startsWith('{') || desc.startsWith('[')) {
    try {
      const j = asRecord(JSON.parse(desc));
      if (j) return j;
    } catch {
      /* plain text / truncated */
    }
  }
  return {};
}

function channelFromSource(source?: string | null): string | null {
  if (!source) return null;
  const s = String(source);
  if (s.startsWith('digital:') || s.startsWith('analog:')) return s.split(':', 2)[1] || null;
  return null;
}

function sourceKind(source?: string | null): string | null {
  if (!source) return null;
  const s = String(source);
  if (s.startsWith('digital:')) return 'COMTRADE digital';
  if (s.startsWith('analog:')) return 'COMTRADE analog';
  if (s.toUpperCase().startsWith('SOE')) return 'SOE';
  if (s.toUpperCase().includes('RELAY')) return 'Relay report';
  return null;
}

function fmtNum(v: unknown, digits = 3): string | null {
  if (typeof v !== 'number' || !Number.isFinite(v)) return null;
  const abs = Math.abs(v);
  if (abs !== 0 && (abs >= 1e4 || abs < 1e-3)) return v.toExponential(2);
  const fixed = v.toFixed(digits);
  return fixed.replace(/(\.\d*?[1-9])0+$/, '$1').replace(/\.0+$/, '');
}

function fmtRms(v: unknown, unitHint?: string): string | null {
  const n = fmtNum(v, 3);
  if (n == null) return null;
  const u = unitHint || '';
  return u ? `${n} ${u}` : n;
}

function transitionText(meta: Record<string, unknown>): string | null {
  if (typeof meta.from === 'undefined' || typeof meta.to === 'undefined') return null;
  return `${meta.from} → ${meta.to}`;
}

function assertState(meta: Record<string, unknown>, eventType: string): string | null {
  const tr = transitionText(meta);
  if (tr) {
    const to = Number(meta.to);
    const from = Number(meta.from);
    if (Number.isFinite(to) && Number.isFinite(from)) {
      if (to > from) return `Asserted (${tr})`;
      if (to < from) return `De-asserted (${tr})`;
    }
    return `Changed (${tr})`;
  }
  const t = normType(eventType);
  if (t.includes('dropout') || t.includes('reset')) return 'De-asserted';
  if (
    t.includes('pickup') ||
    t.includes('trip') ||
    t.includes('operate') ||
    t.includes('inception')
  ) {
    return 'Asserted';
  }
  return null;
}

function unitForChannel(channel: string | null, eventType: string): string {
  if (!channel) {
    const t = normType(eventType);
    if (t.includes('voltage')) return 'V';
    if (t.includes('current')) return 'A';
    return '';
  }
  const c = channel.toUpperCase();
  if (/^V|VA|VB|VC|VN|VAB|VBC|VCA/.test(c) || c.includes('VOLT')) return 'V';
  if (/^I|IA|IB|IC|IN|IG/.test(c) || c.includes('CURR')) return 'A';
  return '';
}

function fact(label: string, value: string | null | undefined): TimelineFact | null {
  if (value == null || value === '' || value === '—' || value === '-') return null;
  return { label, value };
}

export function buildTimelineCardInfo(e: TimelineEntry): TimelineCardInfo {
  const meta = parseMeta(e);
  const typeKey = normType(e.event_type);
  const channel =
    (typeof meta.channel === 'string' && meta.channel) || channelFromSource(e.source);
  const element =
    (typeof meta.element === 'string' && meta.element) ||
    (typeof meta.function === 'string' && meta.function) ||
    null;
  const role =
    (typeof meta.target_role === 'string' && meta.target_role) ||
    (typeof meta.role === 'string' && meta.role) ||
    null;
  const signal =
    (typeof meta.signal === 'string' && meta.signal) ||
    (typeof meta.message === 'string' && meta.message) ||
    null;
  const method = typeof meta.method === 'string' ? meta.method : null;
  const file = typeof meta.file === 'string' ? meta.file : null;
  const unit = unitForChannel(channel, e.event_type);
  const state = assertState(meta, e.event_type);
  const tr = transitionText(meta);

  let title = timelineEventTitle(e.event_type);
  if (element) title = `${element} · ${title}`;

  // Prefer SOE / relay plain-language signal over snake_case label
  if (signal && signal !== e.label && !signal.startsWith('{')) {
    title = element ? `${element} · ${signal}` : signal;
  } else if (e.label && !/^[a-z0-9_]+$/i.test(e.label) && e.label !== e.event_type) {
    title = e.label;
  }

  const parts: string[] = [];
  if (element && role) parts.push(`${element} ${role.toLowerCase()}`);
  else if (element) parts.push(element);
  else if (role) parts.push(role.toLowerCase());
  if (state) parts.push(state.toLowerCase());
  if (channel) parts.push(`on ${channel}`);
  let summary = parts.length
    ? parts.join(' · ').replace(/^\w/, (c) => c.toUpperCase())
    : timelineEventTitle(e.event_type);

  // Analog / inception: clearer sentence
  if (typeKey === 'voltage_change' || typeKey === 'current_increase') {
    const base = fmtRms(meta.baseline_rms, unit);
    const thr = fmtRms(meta.threshold, unit);
    summary = [
      channel ? `${channel}` : timelineEventTitle(e.event_type),
      base ? `baseline ${base}` : null,
      thr ? `threshold ${thr}` : null,
    ]
      .filter(Boolean)
      .join(' · ');
  } else if (typeKey === 'fault_inception') {
    summary = signal || (method ? `Detected by ${method.replace(/_/g, ' ')}` : 'Fault inception');
  } else if (typeKey === '52a_change' || typeKey === '52b_change') {
    const to = meta.to;
    const open = to === 0 || to === '0' || to === false;
    const closed = to === 1 || to === '1' || to === true;
    summary = [
      channel || 'Breaker status',
      open ? 'opened (52a low)' : closed ? 'closed (52a high)' : state,
      tr ? tr : null,
    ]
      .filter(Boolean)
      .join(' · ');
  }

  const facts: TimelineFact[] = [];
  const push = (f: TimelineFact | null) => {
    if (f) facts.push(f);
  };

  push(fact('Element', element));
  push(fact('Target', role));
  push(fact('Channel', channel));
  push(fact('State', state));
  push(fact('Transition', tr && !state?.includes(tr) ? tr : null));
  push(fact('Baseline', fmtRms(meta.baseline_rms, unit)));
  push(fact('Threshold', fmtRms(meta.threshold, unit)));
  push(fact('Method', method ? method.replace(/_/g, ' ') : null));
  push(fact('Signal', signal && signal !== title ? signal : null));
  push(fact('File', file));
  push(fact('Source type', sourceKind(e.source)));

  // Any remaining useful keys (skip dumps / internal)
  for (const [k, v] of Object.entries(meta)) {
    if (HIDDEN_KEYS.has(k)) continue;
    if (
      [
        'channel',
        'element',
        'function',
        'target_role',
        'role',
        'signal',
        'message',
        'method',
        'file',
        'from',
        'to',
        'baseline_rms',
        'threshold',
        'value',
        'asserted',
      ].includes(k)
    ) {
      continue;
    }
    if (v == null || typeof v === 'object') continue;
    if (typeof v === 'number') {
      push(fact(formatCheckName(k), fmtNum(v, 3)));
    } else {
      const s = String(v);
      if (s.length > 120) continue;
      push(fact(formatCheckName(k), s));
    }
  }

  // Plain-text description when not JSON
  if (!facts.length && e.description && !e.description.trim().startsWith('{')) {
    push(fact('Detail', e.description.trim()));
  }

  return { title, summary, facts, transition: tr };
}

/** Normalize timeline event_type for stage matching (strip / case). */
export function matchTimelineType(eventType: string, candidates: string[]): boolean {
  const n = normType(eventType);
  return candidates.some((c) => normType(c) === n);
}
