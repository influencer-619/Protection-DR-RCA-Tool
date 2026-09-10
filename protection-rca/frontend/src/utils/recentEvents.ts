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
  localStorage.setItem(KEY, JSON.stringify([next, ...rest].slice(0, MAX)));
}

export function getLastEvent(): RecentEventRef | null {
  return loadRecentEvents()[0] ?? null;
}
