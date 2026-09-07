import type { AnalysisJob, AnalysisStage } from '@/types';
import styles from './AnalysisProgress.module.css';

interface Props {
  job: AnalysisJob;
  compact?: boolean;
}

function StageIcon({ status }: { status: AnalysisStage['status'] }) {
  if (status === 'done') return <span className={styles.done}>✓</span>;
  if (status === 'running') return <span className={styles.running}>●</span>;
  if (status === 'failed') return <span className={styles.failed}>✕</span>;
  return <span className={styles.pending}>○</span>;
}

export function AnalysisProgress({ job, compact }: Props) {
  return (
    <div className={`${styles.wrap} ${compact ? styles.compact : ''}`}>
      <div className={styles.header}>
        <span className={styles.title}>Analysis pipeline</span>
        <span className={`mono ${styles.pct}`}>{Math.round(job.progress)}%</span>
      </div>
      {job.current_message && (
        <div className={styles.message}>{job.current_message}</div>
      )}
      <ol className={styles.list}>
        {job.stages.map((s) => (
          <li key={s.name} className={`${styles.item} ${styles[s.status]}`}>
            <StageIcon status={s.status} />
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
