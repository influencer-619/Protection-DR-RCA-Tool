import { useCallback, useEffect, useState } from 'react';
import type { QuantitySideMode } from '@/utils/quantitySide';

const KEY = 'protection_rca_quantity_side_v1';

function loadAll(): Record<string, QuantitySideMode> {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, QuantitySideMode>;
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function save(eventId: string, mode: QuantitySideMode) {
  const all = loadAll();
  all[eventId] = mode;
  localStorage.setItem(KEY, JSON.stringify(all));
  try {
    window.dispatchEvent(
      new CustomEvent('protection-rca-quantity-side', { detail: { eventId, mode } }),
    );
  } catch {
    /* ignore */
  }
}

/** Shared Primary / Secondary / Both preference per event (DR, Waveforms, Electrical). */
export function useQuantitySide(eventId: string | undefined): {
  mode: QuantitySideMode;
  setMode: (m: QuantitySideMode) => void;
} {
  const [mode, setModeState] = useState<QuantitySideMode>(() => {
    if (!eventId) return 'secondary';
    return loadAll()[eventId] || 'secondary';
  });

  useEffect(() => {
    if (!eventId) return;
    setModeState(loadAll()[eventId] || 'secondary');
  }, [eventId]);

  useEffect(() => {
    if (!eventId) return;
    const onCustom = (e: Event) => {
      const detail = (e as CustomEvent<{ eventId: string; mode: QuantitySideMode }>).detail;
      if (detail?.eventId === eventId && detail.mode) setModeState(detail.mode);
    };
    const onStorage = (e: StorageEvent) => {
      if (e.key !== KEY || !eventId) return;
      setModeState(loadAll()[eventId] || 'secondary');
    };
    window.addEventListener('protection-rca-quantity-side', onCustom);
    window.addEventListener('storage', onStorage);
    return () => {
      window.removeEventListener('protection-rca-quantity-side', onCustom);
      window.removeEventListener('storage', onStorage);
    };
  }, [eventId]);

  const setMode = useCallback(
    (m: QuantitySideMode) => {
      setModeState(m);
      if (eventId) save(eventId, m);
    },
    [eventId],
  );

  return { mode, setMode };
}
