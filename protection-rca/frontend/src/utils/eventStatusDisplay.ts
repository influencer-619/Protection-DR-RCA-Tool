import type { AnalysisJob, Event } from '@/types';

/** True when the event already has engineer-usable analysis artefacts. */
export function eventHasUsableResults(event: Event | null | undefined): boolean {
  if (!event) return false;
  const decision = String(event.decision_state || '').toUpperCase();
  if (decision.includes('ANALYSIS_COMPLETE') || decision.includes('REVIEW')) return true;
  const fault = String(event.fault_type || '').toUpperCase();
  if (fault && fault !== 'UNKNOWN') return true;
  const extra = (event.extra || {}) as Record<string, unknown>;
  if (extra.protection_summary || extra.report_analysis) return true;
  const casc = (extra.cascade || {}) as Record<string, unknown>;
  if (casc.primary_hypothesis || casc.sequence || casc.rca) return true;
  // combined_ready shell alone is not "done" (avoids unlocking mid-queue incorrectly).
  return false;
}

/** PENDING job that never left the queue (background worker dropped). */
export function isOrphanedPendingJob(job: AnalysisJob | null | undefined, minAgeS = 20): boolean {
  if (!job) return false;
  if (String(job.status || '').toUpperCase() !== 'PENDING') return false;
  if ((job.progress ?? 0) > 0.01) return false;
  if (job.started_at) return false;
  const created = job.created_at ? Date.parse(job.created_at) : NaN;
  if (!Number.isFinite(created)) return false;
  return (Date.now() - created) / 1000 >= minAgeS;
}

/**
 * Display status for badges / strips.
 * Sticky FAILED / ANALYZING must not dominate when results already exist —
 * common after a failed re-run or orphaned background queue on cascade events.
 */
export function effectiveEventStatus(
  event: Event | null | undefined,
  jobStatus?: string | null,
  job?: AnalysisJob | null,
): string {
  const raw = String(event?.status || '').toUpperCase();
  const js = String(jobStatus || job?.status || '').toUpperCase();
  const has = eventHasUsableResults(event);

  if (js === 'RUNNING') return event?.status || 'ANALYZING';

  if ((raw === 'FAILED' || raw === 'ANALYZING' || raw === 'PENDING') && has) {
    if (js === 'PENDING' && !isOrphanedPendingJob(job)) {
      return event?.status || 'ANALYZING';
    }
    return 'REVIEW';
  }

  if (raw === 'ANALYZING' && (js === 'COMPLETED' || js === 'FAILED' || isOrphanedPendingJob(job))) {
    return js === 'FAILED' && !has ? 'FAILED' : 'REVIEW';
  }

  if (!raw && js === 'COMPLETED') return 'REVIEW';
  return event?.status || 'UNKNOWN';
}

/** True while a live pipeline should block Start / Re-run. */
export function isAnalysisBusy(
  job: AnalysisJob | null | undefined,
  _event?: Event | null,
): boolean {
  const st = String(job?.status || '').toUpperCase();
  if (st === 'RUNNING') return true;
  if (st === 'PENDING') return !isOrphanedPendingJob(job);
  return false;
}

/** Latest job FAILED is only "blocking" when there are no usable results yet. */
export function isBlockingAnalysisFailure(
  event: Event | null | undefined,
  jobStatus?: string | null,
): boolean {
  if (String(jobStatus || '').toUpperCase() !== 'FAILED') return false;
  return !eventHasUsableResults(event);
}
