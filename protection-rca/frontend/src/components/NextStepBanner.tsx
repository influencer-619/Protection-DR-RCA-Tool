import { Link } from 'react-router-dom';
import type { PipelineLamp } from '@/components/EventStatusBar';
import styles from './NextStepBanner.module.css';

export interface NextStep {
  title: string;
  detail: string;
  to?: string;
  actionLabel?: string;
  onAction?: () => void;
  actionDisabled?: boolean;
}

/** Derive a single recommended step from pipeline lamps + job — industry-style guided RCA. */
export function deriveNextStep(opts: {
  eventId: string;
  lamps: PipelineLamp[];
  analysisBusy: boolean;
  jobStatus?: string | null;
  onAnalyse?: () => void;
  onConfirmSettings?: () => void;
}): NextStep | null {
  const { eventId, lamps, analysisBusy, jobStatus, onAnalyse } = opts;
  const byKey = Object.fromEntries(lamps.map((l) => [l.key, l]));
  const base = `/events/${eventId}`;

  if (analysisBusy) {
    return {
      title: 'Analysis in progress',
      detail:
        'Watch the progress checklist. When complete, start with Overview → Waveforms → Consistency.',
    };
  }

  if (jobStatus === 'FAILED') {
    return {
      title: 'Analysis failed',
      detail: 'Check COMTRADE validation and uploaded files, then re-run analysis.',
      to: `${base}/comtrade`,
      actionLabel: 'Re-run analysis',
      onAction: onAnalyse,
      actionDisabled: !onAnalyse,
    };
  }

  if (byKey.comtrade?.state === 'pending' || byKey.comtrade?.state === 'error') {
    return {
      title: 'Upload disturbance record',
      detail:
        'Add CFG+DAT (or CFF/ZIP). Professional tools always start from a validated COMTRADE file.',
      to: `${base}/files`,
      actionLabel: 'Go to Files',
    };
  }

  if (jobStatus !== 'COMPLETED' && byKey.protection?.state === 'pending') {
    return {
      title: 'Run analysis',
      detail:
        'Builds timeline, electrical quantities, protection assessment, consistency, and RCA from uploaded files.',
      actionLabel: 'Start analysis',
      onAction: onAnalyse,
      actionDisabled: !onAnalyse,
    };
  }

  if (byKey.settings?.state === 'warn') {
    return {
      title: 'Approve settings file',
      detail:
        'Settings are loaded but not APPROVED / VERIFIED. Approve the uploaded file (and confirm active group), or upload APPROVED_RELAY_BASE_SETTINGS.',
      to: `${base}/consistency`,
      actionLabel: 'Open Consistency',
    };
  }

  if (byKey.consistency?.state === 'error') {
    return {
      title: 'Review consistency findings',
      detail:
        'INCONSISTENT means observed vs verified settings conflict. Inspect evidence before calling malfunction.',
      to: `${base}/consistency`,
      actionLabel: 'Open Consistency',
    };
  }

  if (byKey.consistency?.state === 'warn') {
    return {
      title: 'Consistency unverifiable',
      detail: 'Review which checks need settings or better data, then continue to RCA.',
      to: `${base}/consistency`,
      actionLabel: 'Open Consistency',
    };
  }

  if (byKey.rca?.state === 'warn' || byKey.rca?.state === 'pending') {
    return {
      title: 'Review RCA hypotheses',
      detail: 'Check primary / alternative hypotheses and missing evidence before closing.',
      to: `${base}/rca`,
      actionLabel: 'Open RCA',
    };
  }

  if (byKey.report?.state === 'pending') {
    return {
      title: 'Generate report & review',
      detail: 'Create the disturbance report, then complete engineer disposition on Review.',
      to: `${base}/report`,
      actionLabel: 'Open Report',
    };
  }

  return {
    title: 'Ready for engineer review',
    detail:
      'Walk Waveforms → Sequence of operation → Protection → Consistency → RCA (use Location only when distance/line evidence applies), then Review.',
    to: `${base}/review`,
    actionLabel: 'Open Review',
  };
}

interface Props {
  step: NextStep;
}

export function NextStepBanner({ step }: Props) {
  return (
    <div className={styles.banner} role="status">
      <div className={styles.text}>
        <div className={styles.label}>Recommended next step</div>
        <div className={styles.title}>{step.title}</div>
        <p className={styles.detail}>{step.detail}</p>
      </div>
      <div className={styles.actions}>
        {step.onAction && (
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={step.actionDisabled}
            onClick={step.onAction}
          >
            {step.actionLabel ?? 'Continue'}
          </button>
        )}
        {step.to && !step.onAction && (
          <Link to={step.to} className="btn btn-sm btn-primary">
            {step.actionLabel ?? 'Continue'}
          </Link>
        )}
        {step.to && step.onAction && (
          <Link to={step.to} className="btn btn-sm">
            Details
          </Link>
        )}
      </div>
    </div>
  );
}
