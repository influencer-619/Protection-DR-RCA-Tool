import type { SettingSourceInfo } from '@/types';
import { StatusBadge } from './StatusBadge';
import styles from './SettingSourceBanner.module.css';

interface Props {
  source: SettingSourceInfo;
}

function plainActive(status: string | undefined): string {
  const s = (status || 'NOT VERIFIED').toUpperCase();
  if (s === 'VERIFIED') return 'Confirmed by engineer or file';
  return 'Not confirmed yet — engineer must verify active group';
}

export function SettingSourceBanner({ source }: Props) {
  const active =
    source.active_group_status ?? source.verification_state ?? 'NOT VERIFIED';

  return (
    <div className={styles.banner} role="status">
      <div className={styles.title}>Setting source (bound for this analysis)</div>
      <div className={styles.grid}>
        <div>
          <span className={styles.label}>Source</span>
          <span className={`mono ${styles.value}`}>{source.source}</span>
        </div>
        <div>
          <span className={styles.label}>Version / Group</span>
          <span className={`mono ${styles.value}`}>
            {source.version}
            {source.group ? ` / ${source.group}` : ''}
          </span>
        </div>
        <div>
          <span className={styles.label}>Active group</span>
          <span className={`mono ${styles.value}`}>{active}</span>
          <div className={styles.hint}>{plainActive(active)}</div>
        </div>
        <div>
          <span className={styles.label}>Approval</span>
          <StatusBadge status={source.approval_status ?? 'NOT VERIFIED'} />
        </div>
        <div>
          <span className={styles.label}>Relay</span>
          <span className={`mono ${styles.value}`}>{source.relay_tag ?? '—'}</span>
        </div>
        <div>
          <span className={styles.label}>Effective from</span>
          <span className={`mono ${styles.value}`}>
            {source.effective_from
              ? new Date(source.effective_from).toISOString().slice(0, 10)
              : '—'}
          </span>
        </div>
        <div>
          <span className={styles.label}>Checksum</span>
          <span className={`mono ${styles.hash}`} title={source.checksum ?? undefined}>
            {source.checksum ? `${source.checksum.slice(0, 16)}…` : '—'}
          </span>
        </div>
      </div>
    </div>
  );
}
