import type { ConsistencyFinding } from '@/types';
import { SeverityBadge } from './SeverityBadge';
import { StatusBadge } from './StatusBadge';
import styles from './FindingDetail.module.css';

interface Props {
  finding: ConsistencyFinding;
  onClose?: () => void;
}

function fmt(v: ConsistencyFinding['expected']): string {
  if (v == null) return '—';
  if (typeof v === 'string') return v;
  return JSON.stringify(v);
}

export function FindingDetail({ finding, onClose }: Props) {
  return (
    <div className={styles.detail}>
      <div className={styles.header}>
        <div>
          <div className={styles.id}>{finding.finding_id}</div>
          <h3>
            {finding.element} — {finding.check_type.replace(/_/g, ' ')}
          </h3>
        </div>
        <div className="badge-row">
          <StatusBadge status={finding.status} />
          <SeverityBadge severity={finding.severity} />
          {onClose && (
            <button type="button" className="btn btn-sm btn-ghost" onClick={onClose}>
              Close
            </button>
          )}
        </div>
      </div>

      <div className={styles.grid}>
        <div>
          <div className={styles.label}>Expected</div>
          <pre className={styles.pre}>{fmt(finding.expected)}</pre>
        </div>
        <div>
          <div className={styles.label}>Observed</div>
          <pre className={styles.pre}>{fmt(finding.observed)}</pre>
        </div>
      </div>

      <div className={styles.section}>
        <div className={styles.label}>Setting source</div>
        <div className="mono">{finding.setting_source ?? '—'} ({finding.setting_version ?? 'n/a'})</div>
      </div>

      {finding.explanation && (
        <div className={styles.section}>
          <div className={styles.label}>Explanation</div>
          <p>{finding.explanation}</p>
        </div>
      )}

      <div className={styles.footer}>
        {finding.confidence != null && (
          <span className="mono">Confidence: {(finding.confidence * 100).toFixed(0)}%</span>
        )}
        {finding.rule_version && <span className="mono">Rule: {finding.rule_version}</span>}
        {finding.evidence_ids && finding.evidence_ids.length > 0 && (
          <span className="mono">Evidence: {finding.evidence_ids.join(', ')}</span>
        )}
      </div>
    </div>
  );
}
