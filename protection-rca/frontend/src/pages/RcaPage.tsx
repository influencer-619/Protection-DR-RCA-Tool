import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { RcaHypothesis, SupportingScoreStatus } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState } from '@/components/EmptyState';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import { formatConfidencePct, humanizeEvidenceToken } from '@/utils/evidenceLabels';
import { CombinedPageHeader } from '@/components/CombinedPageHeader';
import styles from './RcaPage.module.css';

function scoreUnavailable(s?: SupportingScoreStatus | null): boolean {
  if (!s) return true;
  return !s.available || String(s.status || '').toUpperCase() === 'NOT_AVAILABLE';
}

export function RcaPage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision } = useEventOrWorkspace(id);
  const [hyps, setHyps] = useState<RcaHypothesis[]>([]);
  const [mlScore, setMlScore] = useState<SupportingScoreStatus | null>(null);
  const [simScore, setSimScore] = useState<SupportingScoreStatus | null>(null);

  useEffect(() => {
    if (!id) return;
    void api
      .getRca(id)
      .then((r) => {
        setHyps(r.hypotheses);
        setMlScore(r.supporting_scores?.ml ?? null);
        setSimScore(r.supporting_scores?.similarity ?? null);
      })
      .catch(() => {
        setHyps([]);
        setMlScore(null);
        setSimScore(null);
      });
  }, [id, analysisRevision]);

  const primary = hyps.find((h) => h.rank === 1) ?? hyps[0];

  if (!hyps.length) {
    return (
      <EmptyState
        title="No RCA hypotheses yet"
        description="Root-cause hypotheses are produced after analysis from electrical, protection, and consistency evidence. The system will not invent a cause when data is insufficient."
        tips={[
          'Complete analysis first (Overview → Run analysis)',
          'RCA ranks hypotheses from fault type, operated protection (any scheme), and consistency — not distance-only',
          'Relay misoperation stays INCONCLUSIVE until active settings are verified',
        ]}
        actions={[
          { label: 'Open Overview', to: id ? `/events/${id}/overview` : '/events' },
          { label: 'Open Consistency', to: id ? `/events/${id}/consistency` : '/events' },
        ]}
      />
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 12 }}>
        <CombinedPageHeader
          title="Root cause analysis"
          subtitle="Primary hypothesis, evidence balance, uncertainty"
        />
      </div>

      {scoreUnavailable(mlScore) && scoreUnavailable(simScore) ? (
        <p className="subtitle" style={{ marginTop: 0, marginBottom: 12 }}>
          Scoring uses deterministic, consistency, and electrical evidence only (ML and
          historical similarity not loaded — weight contribution zero).
        </p>
      ) : (
        (scoreUnavailable(mlScore) || scoreUnavailable(simScore)) && (
          <p className="subtitle" style={{ marginTop: 0, marginBottom: 12 }}>
            {scoreUnavailable(mlScore) && 'ML anomaly scores not available (weight zero). '}
            {scoreUnavailable(simScore) &&
              'Historical similarity not available (weight zero).'}
          </p>
        )
      )}

      {primary && (
        <div className="ux-strip">
          <div className="ux-item">
            <div className="ux-label">Why</div>
            <div className="ux-value">{primary.title}</div>
          </div>
          <div className="ux-item">
            <div className="ux-label">Confidence</div>
            <div className={`ux-value ${primary.confidence_level !== 'HIGH' ? 'uncertain' : ''}`}>
              {primary.status} · {formatConfidencePct(primary.confidence)}
            </div>
          </div>
          <div className="ux-item">
            <div className="ux-label">Supporting</div>
            <div className="ux-value mono">{primary.supporting_evidence_ids?.length ?? 0} items</div>
          </div>
          <div className="ux-item">
            <div className="ux-label">Contradicting</div>
            <div className="ux-value mono">{primary.contradicting_evidence_ids?.length ?? 0}</div>
          </div>
          <div className="ux-item">
            <div className="ux-label">Missing / verify</div>
            <div className="ux-value uncertain">
              {primary.missing_evidence?.[0]
                ? humanizeEvidenceToken(primary.missing_evidence[0])
                : 'None'}
            </div>
          </div>
        </div>
      )}

      {primary && (
        <div className={`${styles.primary} panel`}>
          <div className="panel-header">
            <span>Primary hypothesis</span>
            <div className="badge-row">
              <StatusBadge status={primary.status} />
              <span className={styles.score} title={primary.hypothesis_code ?? undefined}>
                {formatConfidencePct(primary.confidence)}
              </span>
            </div>
          </div>
          <div className="panel-body">
            <h2 className={styles.title}>{primary.title}</h2>
            <p className={styles.statement}>{primary.statement}</p>

            <div className={styles.columns}>
              <div>
                <h4>Supporting evidence</h4>
                <ul className={styles.evidenceList}>
                  {(primary.supporting_evidence_ids ?? []).map((e) => (
                    <li key={e}>
                      {id ? (
                        <Link to={`/events/${id}/evidence`} title={e}>
                          {humanizeEvidenceToken(e)}
                        </Link>
                      ) : (
                        <span title={e}>{humanizeEvidenceToken(e)}</span>
                      )}
                    </li>
                  ))}
                  {!primary.supporting_evidence_ids?.length && (
                    <li className={styles.emptyNote}>None recorded</li>
                  )}
                </ul>
              </div>
              <div>
                <h4>Contradicting</h4>
                <ul className={styles.evidenceList}>
                  {(primary.contradicting_evidence_ids ?? []).map((e) => (
                    <li key={e} title={e}>
                      {humanizeEvidenceToken(e)}
                    </li>
                  ))}
                  {!primary.contradicting_evidence_ids?.length && (
                    <li className={styles.emptyNote}>None recorded</li>
                  )}
                </ul>
              </div>
              <div>
                <h4>Missing evidence</h4>
                <ul className={styles.missing}>
                  {(primary.missing_evidence ?? []).map((e) => (
                    <li key={e} title={e}>
                      {humanizeEvidenceToken(e)}
                    </li>
                  ))}
                  {!primary.missing_evidence?.length && (
                    <li className={styles.emptyNote}>None — required evidence is present</li>
                  )}
                </ul>
              </div>
            </div>

            {primary.causal_chain && (
              <div className={styles.chain}>
                <h4>Step-by-step evidence trail</h4>
                <p className="subtitle" style={{ marginTop: 0, marginBottom: 8 }}>
                  Waveforms → digitals (ANSI) → SOE / sequence → settings → conclusion
                </p>
                <ol>
                  {primary.causal_chain.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ol>
              </div>
            )}

            {primary.recommended_actions && (
              <div className={styles.actions}>
                <h4>Recommended verification</h4>
                <ul>
                  {primary.recommended_actions.map((a) => (
                    <li key={a}>{a}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
