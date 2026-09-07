import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useEvent } from '@/hooks/useEvent';
import { useAnalysisStatus } from '@/hooks/useAnalysisStatus';
import type { AnalysisJob, Event } from '@/types';

export interface EventWorkspaceValue {
  eventId: string | undefined;
  event: Event | null;
  loading: boolean;
  error: string | null;
  reload: () => Promise<void>;
  applyEvent: (event: Event) => void;
  job: AnalysisJob | null;
  reloadJob: () => Promise<void>;
  /** Increments when analysis finishes so tabs refetch all data */
  analysisRevision: number;
  analysisBusy: boolean;
}

const EventWorkspaceContext = createContext<EventWorkspaceValue | null>(null);

export function EventWorkspaceProvider({
  eventId,
  children,
}: {
  eventId: string | undefined;
  children: ReactNode;
}) {
  const { event, setEvent, loading, error, reload } = useEvent(eventId);
  const { job, reload: reloadJob } = useAnalysisStatus(eventId, 2000);
  const [analysisRevision, setAnalysisRevision] = useState(0);
  const prevJobStatus = useRef<string | null | undefined>(undefined);

  const applyEvent = useCallback(
    (next: Event) => {
      setEvent(next);
    },
    [setEvent],
  );

  useEffect(() => {
    const status = job?.status ?? null;
    const prev = prevJobStatus.current;
    prevJobStatus.current = status;
    if (prev === undefined) return; // skip initial mount
    if (prev === status) return;
    if (status === 'COMPLETED' || status === 'FAILED') {
      void reload();
      setAnalysisRevision((n) => n + 1);
    }
  }, [job?.status, reload]);

  const analysisBusy = job?.status === 'PENDING' || job?.status === 'RUNNING';

  const value = useMemo(
    () => ({
      eventId,
      event,
      loading,
      error,
      reload,
      applyEvent,
      job,
      reloadJob,
      analysisRevision,
      analysisBusy,
    }),
    [
      eventId,
      event,
      loading,
      error,
      reload,
      applyEvent,
      job,
      reloadJob,
      analysisRevision,
      analysisBusy,
    ],
  );

  return (
    <EventWorkspaceContext.Provider value={value}>{children}</EventWorkspaceContext.Provider>
  );
}

export function useEventWorkspace(): EventWorkspaceValue {
  const ctx = useContext(EventWorkspaceContext);
  if (!ctx) {
    throw new Error('useEventWorkspace must be used within EventWorkspaceProvider');
  }
  return ctx;
}

/** Prefer workspace when inside EventLayout; otherwise local fetch. */
export function useEventOrWorkspace(eventId: string | undefined) {
  const ctx = useContext(EventWorkspaceContext);
  const local = useEvent(eventId);
  if (ctx && ctx.eventId === eventId) {
    return {
      event: ctx.event,
      loading: ctx.loading,
      error: ctx.error,
      reload: ctx.reload,
      applyEvent: ctx.applyEvent,
      analysisRevision: ctx.analysisRevision,
      job: ctx.job,
      reloadJob: ctx.reloadJob,
      analysisBusy: ctx.analysisBusy,
    };
  }
  return {
    event: local.event,
    loading: local.loading,
    error: local.error,
    reload: local.reload,
    applyEvent: (_e: Event) => {
      void local.reload();
    },
    analysisRevision: 0,
    job: null as AnalysisJob | null,
    reloadJob: async () => undefined,
    analysisBusy: false,
  };
}
