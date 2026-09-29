import type { AnalysisJob, AnalysisStage } from '@/types';
import styles from './AnalysisProgress.module.css';

interface Props {
  job: AnalysisJob;
  compact?: boolean;
}

const STAGE_ICON: Record<AnalysisStage['status'], string> = {
  done: '✓',
  running: '●',
  failed: '✕',
  pending: '○',
  skipped: '–',
};

const STAGE_CLASS: Record<AnalysisStage['status'], string> = {
  done: styles.stDone,
  running: styles.stRunning,
  failed: styles.stFailed,
  pending: styles.stPending,
  skipped: styles.stPending,
};

export function AnalysisProgress({ job, compact }: Props) {
  const pct = Math.max(0, Math.min(100, Math.round(job.progress ?? 0)));
  const failed = job.status === 'FAILED';
  return (
    <div className={`${styles.wrap} ${compact ? styles.compact : ''}`}>
      <div className={styles.header}>
        <span className={styles.title}>Analysis pipeline</span>
        {job.current_message && <span className={styles.message}>{job.current_message}</span>}
        <span className={`mono ${styles.pct}`}>{pct}%</span>
      </div>
      <div className={styles.bar} aria-hidden>
        <div
          className={`${styles.fill} ${failed ? styles.fillFailed : ''}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <ol className={styles.list}>
        {job.stages.map((s) => (
          <li key={s.name} className={`${styles.item} ${STAGE_CLASS[s.status] ?? ''}`}>
            <span className={styles.icon}>{STAGE_ICON[s.status] ?? '○'}</span>
            <span className={styles.label}>{s.label}</span>
          </li>
        ))}
      </ol>
      {job.component_versions && (
        <div className={styles.versions}>
          {Object.entries(job.component_versions).map(([k, v]) => (
            <span key={k} className="mono">
              {k}:{v}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
