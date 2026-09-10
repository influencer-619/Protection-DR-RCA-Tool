/** Persist DR viewer display preferences (SIGRA-style user profiles). */

export interface DrDisplayProfile {
  id: string;
  name: string;
  showAnalog: boolean;
  showDigital: boolean;
  showRms: boolean;
  selectedChannelNames: string[];
  colors?: Record<string, string>;
  layout?: 'stacked' | 'split';
  updatedAt: string;
}

const KEY = 'protection_rca_dr_profiles_v1';
const ACTIVE_KEY = 'protection_rca_dr_active_profile';

export function loadProfiles(): DrDisplayProfile[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as DrDisplayProfile[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function saveProfiles(profiles: DrDisplayProfile[]) {
  localStorage.setItem(KEY, JSON.stringify(profiles.slice(0, 20)));
}

export function getActiveProfileId(): string | null {
  return localStorage.getItem(ACTIVE_KEY);
}

export function setActiveProfileId(id: string | null) {
  if (id) localStorage.setItem(ACTIVE_KEY, id);
  else localStorage.removeItem(ACTIVE_KEY);
}

export function upsertProfile(profile: DrDisplayProfile) {
  const all = loadProfiles().filter((p) => p.id !== profile.id);
  all.unshift(profile);
  saveProfiles(all);
  setActiveProfileId(profile.id);
}
