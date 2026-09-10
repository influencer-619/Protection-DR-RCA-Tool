/** Persist last DR workspace session per event (SIGRA-style session memory). */

export interface DrSessionState {
  eventId: string;
  cursorA: number | null;
  cursorB: number | null;
  localId: string;
  remoteId: string;
  updatedAt: string;
}

const KEY = 'protection_rca_dr_session_v1';

function loadAll(): Record<string, DrSessionState> {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, DrSessionState>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function loadDrSession(eventId: string): DrSessionState | null {
  return loadAll()[eventId] ?? null;
}

export function saveDrSession(state: DrSessionState) {
  const all = loadAll();
  all[state.eventId] = { ...state, updatedAt: new Date().toISOString() };
  const keys = Object.keys(all);
  if (keys.length > 40) {
    const sorted = keys
      .map((k) => all[k])
      .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1))
      .slice(0, 40);
    const trimmed: Record<string, DrSessionState> = {};
    for (const s of sorted) trimmed[s.eventId] = s;
    localStorage.setItem(KEY, JSON.stringify(trimmed));
    return;
  }
  localStorage.setItem(KEY, JSON.stringify(all));
}

export function markDrVisited(eventId: string) {
  try {
    sessionStorage.setItem(`protection_rca_dr_visited_${eventId}`, '1');
  } catch {
    /* ignore */
  }
}

export function wasDrVisited(eventId: string): boolean {
  try {
    return sessionStorage.getItem(`protection_rca_dr_visited_${eventId}`) === '1';
  } catch {
    return false;
  }
}
