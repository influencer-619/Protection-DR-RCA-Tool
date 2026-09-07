import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { EvidenceItem } from '@/types';
import { EvidenceDrawer } from '@/components/EvidenceDrawer';
import { EmptyState } from '@/components/EmptyState';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';

const MEANING = [
  {
    key: 'SUPPORTING',
    label: 'Supports',
    hint: 'Measurements or checks that line up with the working conclusion',
  },
  {
    key: 'CONTRADICTING',
    label: 'Conflicts',
    hint: 'Something does not match settings or expected behaviour — investigate, do not auto-blame the relay',
  },
  {
    key: 'MISSING',
    label: 'Missing',
    hint: 'Needed data or verification is not available yet',
  },
  {
    key: 'NEUTRAL',
    label: 'Notes',
    hint: 'Context that helps the engineer but does not vote for/against alone',
  },
] as const;

export function EvidencePage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision } = useEventOrWorkspace(id);
  const [items, setItems] = useState<EvidenceItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    void api
      .getEvidence(id)
      .then(setItems)
      .finally(() => setLoading(false));
  }, [id, analysisRevision]);

  const supporting = items.filter((i) => i.polarity === 'SUPPORTING');
  const contradicting = items.filter((i) => i.polarity === 'CONTRADICTING');
  const missing = items.filter((i) => i.polarity === 'MISSING');
  const other = items.filter(
    (i) => !['SUPPORTING', 'CONTRADICTING', 'MISSING'].includes(i.polarity),
  );

  if (!loading && items.length === 0) {
    return (
      <EmptyState
        title="No evidence linked yet"
        description="Evidence is built when analysis runs — RMS samples, consistency checks, and protection outcomes that support or challenge the RCA."
        actions={[
          { label: 'Re-run analysis', to: id ? `/events/${id}/overview` : undefined, primary: true },
          { label: 'Open RCA', to: id ? `/events/${id}/rca` : undefined },
        ]}
        tips={[
          'Upload COMTRADE + settings, then Re-run analysis.',
          'Each card below will explain what was measured or checked in plain language.',
        ]}
      />
    );
  }

  return (
    <div className="stack-md">
      <div className="page-header" style={{ padding: 0, marginBottom: 0 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Evidence</h1>
          <p className="subtitle">
            Plain-language facts behind the RCA — what supports the conclusion, what conflicts,
            and what is still missing
          </p>
        </div>
      </div>

      <div className="alert alert-info" role="note">
        <strong>How to read this tab:</strong> open a row to see the explanation. Prefer Conflicts
        and Missing first, then Supports. Link back to{' '}
        <Link to={`/events/${id}/consistency`}>Consistency</Link> and{' '}
        <Link to={`/events/${id}/rca`}>RCA</Link> for decisions — this page is the audit trail, not
        a control screen.
      </div>

      <div className="grid-kpis">
        <div className="kpi-card ok">
          <div className="kpi-label">Supports</div>
          <div className="kpi-value">{supporting.length}</div>
        </div>
        <div className="kpi-card danger">
          <div className="kpi-label">Conflicts</div>
          <div className="kpi-value">{contradicting.length}</div>
        </div>
        <div className="kpi-card warn">
          <div className="kpi-label">Missing</div>
          <div className="kpi-value">{missing.length}</div>
        </div>
        <div className="kpi-card info">
          <div className="kpi-label">Notes</div>
          <div className="kpi-value">{other.length}</div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">Legend</div>
        <div className="panel-body" style={{ display: 'grid', gap: 8 }}>
          {MEANING.map((m) => (
            <div key={m.key} style={{ fontSize: '0.85rem' }}>
              <strong>{m.label}</strong>
              <span style={{ color: 'var(--text-muted)' }}> — {m.hint}</span>
            </div>
          ))}
        </div>
      </div>

      <EvidenceDrawer items={items} title="Evidence items (click to expand)" />
    </div>
  );
}
