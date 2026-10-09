import type { SettingSourceInfo } from '@/types';
import { StatusBadge } from './StatusBadge';
import styles from './SettingSourceBanner.module.css';

interface Props {
  source: SettingSourceInfo;
  /** Override relay display (combined cascade / multi-end labels). */
  relayDisplay?: string | null;
  /** Extra note under the title (e.g. initiator settings bound). */
  note?: string | null;
}

function plainActive(status: string | undefined, sourceMissing: boolean): string {
  if (sourceMissing) return 'No settings file bound — upload settings to enable checks';
  const s = (status || 'NOT VERIFIED').toUpperCase();
  if (s === 'VERIFIED') return 'Confirmed by engineer or file';
  return 'Uploaded settings are treated as APPROVED automatically';
}

export function SettingSourceBanner({ source, relayDisplay, note }: Props) {
  const active =
    source.active_group_status ?? source.verification_state ?? 'NOT VERIFIED';
  const src = String(source.source || '').toUpperCase();
  const sourceMissing =
    !src ||
    src === 'NOT AVAILABLE' ||
    src === 'NOT_AVAILABLE' ||
    src === 'NOT VERIFIED' ||
    src === 'UNKNOWN';
  const relay = relayDisplay || source.relay_tag || '—';

  return (
    <div className={styles.banner} role="status">
      <div className={styles.title}>Setting source (bound for this analysis)</div>
      {note ? <div className={styles.hint} style={{ marginBottom: 8 }}>{note}</div> : null}
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
          <div className={styles.hint}>{plainActive(active, sourceMissing)}</div>
        </div>
        <div>
          <span className={styles.label}>Approval</span>
          <StatusBadge status={source.approval_status ?? 'NOT VERIFIED'} />
        </div>
        <div>
          <span className={styles.label}>Relay</span>
          <span className={`mono ${styles.value}`}>{relay}</span>
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
