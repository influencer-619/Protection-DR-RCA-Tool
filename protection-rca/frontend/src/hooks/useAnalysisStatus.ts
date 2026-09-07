import { useCallback, useEffect, useState } from 'react';
import { api } from '@/services/api';
import type { AnalysisJob } from '@/types';

export function useAnalysisStatus(eventId: string | undefined, pollMs = 0) {
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!eventId) {
      setJob(null);
      setLoading(false);
      return;
    }
    try {
      const data = await api.getAnalysisStatus(eventId);
      setJob(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load analysis status');
    } finally {
      setLoading(false);
    }
  }, [eventId]);

  useEffect(() => {
    setLoading(true);
    void reload();
  }, [reload]);

  useEffect(() => {
    if (!pollMs || !eventId) return;
    const id = window.setInterval(() => {
      void reload();
    }, pollMs);
    return () => window.clearInterval(id);
  }, [pollMs, eventId, reload]);

  return { job, loading, error, reload };
}
