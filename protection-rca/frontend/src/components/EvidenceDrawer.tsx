import { useMemo, useState } from 'react';
import type { EvidenceItem } from '@/types';
import { formatEvidenceSummary } from '@/utils/formatEvidenceSummary';
import { formatFindingValue } from '@/utils/findingValue';
import styles from './EvidenceDrawer.module.css';

interface Props {
  items: EvidenceItem[];
  title?: string;
}

const POLARITY_LABEL: Record<string, string> = {
  SUPPORTING: 'Supports conclusion',
  CONTRADICTING: 'Conflicts / investigate',
  MISSING: 'Missing data',
  NEUTRAL: 'Context / note',
};

function polarityClass(p: EvidenceItem['polarity']): string {
  if (p === 'SUPPORTING') return styles.supporting;
  if (p === 'CONTRADICTING') return styles.contradicting;
  if (p === 'MISSING') return styles.missing;
  return styles.neutral;
}

function sourceLabel(s: string): string {
  const u = (s || '').toUpperCase();
  if (u === 'COMTRADE') return 'From COMTRADE record';
  if (u === 'CALCULATION') return 'From calculation';
  if (u === 'PROTECTION_RULE') return 'From consistency / protection rule';
  if (u === 'BASE_SETTINGS' || u.includes('SETTING')) return 'From settings';
  if (u === 'SOE') return 'From SOE';
  return s || 'Source unknown';
}

function friendlyTitle(title: string | undefined): string {
  if (!title) return 'Evidence item';
  return title
    .replace(/^Measured RMS\s*-\s*channel\s*/i, 'Measured RMS — ')
    .replace(/^Consistency check\s*-\s*/i, 'Consistency check — ');
}

function refLine(item: EvidenceItem): string | null {
  const r = item.references;
  if (!r || typeof r !== 'object') return null;
  const parts: string[] = [];
  if (r.expected != null) parts.push(`Expected: ${formatFindingValue(r.expected)}`);
  if (r.observed != null) parts.push(`Observed: ${formatFindingValue(r.observed)}`);
  if (r.value != null && r.expected == null) {
    parts.push(`Value: ${String(r.value)}${r.unit ? ` ${r.unit}` : ''}`);
  }
  return parts.length ? parts.join('\n') : null;
}

function EvidenceNode({ item, depth = 0 }: { item: EvidenceItem; depth?: number }) {
  const [open, setOpen] = useState(depth < 1);
  const hasChildren = Boolean(item.children?.length);
  const summary = formatEvidenceSummary(item.summary) || refLine(item);
  const canExpand = hasChildren || !!summary;

  return (
    <div className={styles.node} style={{ marginLeft: depth * 14 }}>
      <button
        type="button"
        className={`${styles.head} ${polarityClass(item.polarity)}`}
        onClick={() => canExpand && setOpen((o) => !o)}
      >
        <span className={styles.chev}>{canExpand ? (open ? '▾' : '▸') : '·'}</span>
        <span className={styles.title}>{friendlyTitle(item.title)}</span>
        <span className={styles.polBadge}>{POLARITY_LABEL[item.polarity] ?? item.polarity}</span>
        {item.confidence != null && item.confidence > 0 && (
          <span className={`mono ${styles.conf}`}>
            {(item.confidence * 100).toFixed(0)}%
          </span>
        )}
      </button>
      {open && (
        <div className={styles.body}>
          {summary && <p className={styles.summary}>{summary}</p>}
          <div className={styles.meta}>
            <span>{sourceLabel(item.source_type)}</span>
            {item.t_us != null && (
              <span className="mono">t = {(item.t_us / 1000).toFixed(2)} ms</span>
            )}
          </div>
          {item.children?.map((c) => (
            <EvidenceNode key={c.id} item={c} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

export function EvidenceDrawer({ items, title = 'Evidence list' }: Props) {
  const sorted = useMemo(() => {
    const order = { CONTRADICTING: 0, MISSING: 1, SUPPORTING: 2, NEUTRAL: 3 } as const;
    return [...items].sort(
      (a, b) => (order[a.polarity] ?? 9) - (order[b.polarity] ?? 9),
    );
  }, [items]);

  return (
    <div className={styles.drawer}>
      <div className={styles.header}>{title}</div>
      <div className={styles.list}>
        {sorted.length === 0 && (
          <div className="empty-state">No evidence items for this event yet.</div>
        )}
        {sorted.map((item) => (
          <EvidenceNode key={item.id} item={item} />
        ))}
      </div>
    </div>
  );
}
