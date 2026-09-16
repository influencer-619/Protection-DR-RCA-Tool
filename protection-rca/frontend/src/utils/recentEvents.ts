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

export function loadRecentEvents(): RecentEventRef[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as RecentEventRef[];
    return Array.isArray(parsed) ? parsed : [];
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
  const next: RecentEventRef = {
    id: ev.id,
    event_id: ev.event_id,
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

export function clearRecentEvents() {
  localStorage.removeItem(KEY);
}

export function getLastEvent(): RecentEventRef | null {
  return loadRecentEvents()[0] ?? null;
}
