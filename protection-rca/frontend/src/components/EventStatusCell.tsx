import { StatusBadge } from '@/components/StatusBadge';
import type { Event } from '@/types';

interface Props {
  event: Event;
  jobError?: string | null;
}

/**
 * Prefer analysis outcome over sticky FAILED when decision/RCA already exist.
 * FAILED still shown with error tooltip when that is the latest job state.
 */
export function EventStatusCell({ event, jobError }: Props) {
  const status = (event.status || '').toUpperCase();
  const decision = (event.decision_state || '').toUpperCase();
  const hasResults =
    !!event.fault_type ||
    decision.includes('ANALYSIS_COMPLETE') ||
    decision.includes('REVIEW');

  if (status === 'FAILED' && hasResults) {
    const tip = [
      'Latest analysis job failed — prior results still shown.',
      jobError || 'Re-run analysis to refresh.',
      decision ? `Decision: ${decision.replace(/_/g, ' ')}` : '',
    ]
      .filter(Boolean)
      .join('\n');
    return (
      <span style={{ display: 'inline-flex', flexDirection: 'column', gap: 2 }}>
        <StatusBadge status="FAILED" title={tip} />
        {decision && (
          <StatusBadge
            status={decision}
            label={decision.includes('WARN') ? 'WARNINGS' : 'HAS RESULTS'}
            title={tip}
          />
        )}
      </span>
    );
  }

  if (status === 'FAILED') {
    return (
      <StatusBadge
        status="FAILED"
        title={jobError || 'Analysis job failed — open event and check job error / re-run.'}
      />
    );
  }

  return <StatusBadge status={event.status} />;
}
