/** Recently opened events — habit trigger for “Continue last”. */

export interface RecentEventRef {
  id: string;
  event_id: string;
  feeder?: string | null;
  status?: string | null;
  openedAt: string;
}

const KEY = 'protection_rca_recent_events_v1';
const MAX = 12;

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;

export function looksLikeUuid(value: string | null | undefined): boolean {
  return Boolean(value && UUID_RE.test(value.trim()));
}

/** Human label for chips / Continue button — never a raw UUID. */
export function recentEventLabel(ref: Pick<RecentEventRef, 'id' | 'event_id'>): string {
  const code = (ref.event_id || '').trim();
  if (code && !looksLikeUuid(code)) return code;
  const short = (ref.id || '').replace(/-/g, '').slice(0, 8);
  return short ? `Event ${short}` : 'Event';
}

export function recentEventDetail(ref: RecentEventRef): string {
  const parts = [recentEventLabel(ref)];
  if (ref.feeder) parts.push(String(ref.feeder));
  if (ref.status) parts.push(String(ref.status).replace(/_/g, ' '));
  return parts.join(' · ');
}

export function loadRecentEvents(): RecentEventRef[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as RecentEventRef[];
    if (!Array.isArray(parsed)) return [];
    return parsed
      .filter((r) => r && typeof r.id === 'string' && r.id)
      .map((r) => ({
        id: r.id,
        event_id: String(r.event_id || r.id),
        feeder: r.feeder ?? null,
        status: r.status ?? null,
        openedAt: r.openedAt || new Date().toISOString(),
      }));
  } catch {
    return [];
  }
}

function saveRecentEvents(rows: RecentEventRef[]) {
  if (!rows.length) {
    localStorage.removeItem(KEY);
    return;
  }
  localStorage.setItem(KEY, JSON.stringify(rows.slice(0, MAX)));
}

export function touchRecentEvent(ev: {
  id: string;
  event_id: string;
  feeder?: string | null;
  status?: string | null;
}) {
  const code = (ev.event_id || '').trim();
  // Prefer human event code; never persist a bare UUID as the display code when avoidable
  const eventCode =
    code && !looksLikeUuid(code) ? code : looksLikeUuid(ev.id) ? ev.id : code || ev.id;

  const next: RecentEventRef = {
    id: ev.id,
    event_id: eventCode,
    feeder: ev.feeder ?? null,
    status: ev.status ?? null,
    openedAt: new Date().toISOString(),
  };
  const rest = loadRecentEvents().filter((r) => r.id !== ev.id);
  saveRecentEvents([next, ...rest]);
}

/** Drop a deleted (or missing) event from the Continue / recent list. */
export function removeRecentEvent(id: string) {
  const next = loadRecentEvents().filter((r) => r.id !== id && r.event_id !== id);
  saveRecentEvents(next);
}

/** Keep only events that still exist (by UUID id). Clears Continue when none remain. */
export function pruneRecentEvents(existingIds: Iterable<string>): RecentEventRef[] {
  const keep = new Set(existingIds);
  const next = loadRecentEvents().filter((r) => keep.has(r.id));
  saveRecentEvents(next);
  return next;
}

/**
 * Prune missing events and refresh human labels (event_id / feeder / status)
 * from the live events list so Recent chips never show raw UUIDs.
 */
export function syncRecentEvents(
  events: Array<{
    id: string;
    event_id?: string | null;
    feeder?: string | null;
    status?: string | null;
  }>,
): RecentEventRef[] {
  const byId = new Map(events.map((e) => [e.id, e]));
  const next = loadRecentEvents()
    .filter((r) => byId.has(r.id))
    .map((r) => {
      const live = byId.get(r.id)!;
      const code = (live.event_id || '').trim();
      return {
        ...r,
        event_id: code && !looksLikeUuid(code) ? code : r.event_id,
        feeder: live.feeder ?? r.feeder ?? null,
        status: live.status ?? r.status ?? null,
      };
    });
  saveRecentEvents(next);
  return next;
}

export function clearRecentEvents() {
  localStorage.removeItem(KEY);
}

export function getLastEvent(): RecentEventRef | null {
  return loadRecentEvents()[0] ?? null;
}
