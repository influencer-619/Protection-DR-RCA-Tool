import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { RcaHypothesis } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState } from '@/components/EmptyState';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import { humanizeEvidenceToken } from '@/utils/evidenceLabels';
import { schemeLabel } from '@/utils/schemeContext';
import styles from './RcaPage.module.css';

export function RcaPage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision } = useEventOrWorkspace(id);
  const [hyps, setHyps] = useState<RcaHypothesis[]>([]);
  const [tagChoices, setTagChoices] = useState<Array<{ token: string; label: string }>>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [schemeInfo, setSchemeInfo] = useState<string | null>(null);
  const [enrichMsg, setEnrichMsg] = useState<string | null>(null);
  const [enrichBusy, setEnrichBusy] = useState(false);

  useEffect(() => {
    if (!id) return;
    void api.getRca(id).then(setHyps).catch(() => setHyps([]));
    void api
      .getCauseEvidence(id)
      .then((res) => {
        setTagChoices(res.tag_choices || []);
        setSelected(new Set((res.items || []).map((i) => i.token)));
        const primary = (res.scheme as { primary?: { scheme_id?: string; label?: string } } | undefined)
          ?.primary;
        if (primary?.scheme_id) {
          setSchemeInfo(primary.label || schemeLabel(primary.scheme_id));
        } else {
          setSchemeInfo(null);
        }
      })
      .catch(() => {
        setTagChoices([]);
        setSelected(new Set());
      });
  }, [id, analysisRevision]);

  const primary = hyps.find((h) => h.rank === 1) ?? hyps[0];
  const alts = hyps.filter((h) => h.id !== primary?.id);

  const toggleTag = (token: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(token)) next.delete(token);
      else next.add(token);
      return next;
    });
  };

  const saveCauseEvidence = async () => {
    if (!id) return;
    setEnrichBusy(true);
    setEnrichMsg(null);
    try {
      await api.putCauseEvidence(id, { tokens: [...selected] });
      setEnrichMsg('Cause evidence saved. Re-run analysis on Overview to re-score RCA.');
    } catch (e) {
      setEnrichMsg(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setEnrichBusy(false);
    }
  };

  if (!hyps.length) {
    return (
      <EmptyState
        title="No RCA hypotheses yet"
        description="Root-cause hypotheses are produced after analysis from electrical, protection, and consistency evidence. The system will not invent a cause when data is insufficient."
        tips={[
          'Complete analysis first (Overview → Run analysis)',
          'RCA ranks hypotheses from fault type, operated protection (any scheme), and consistency — not distance-only',
          'Add field cause evidence (lightning / vegetation / cable) here after analysis, then re-run',
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
      <div className="page-header" style={{ padding: 0, marginBottom: 12 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Root cause analysis</h1>
          <p className="subtitle">
            Primary hypothesis, alternatives, evidence balance, uncertainty
            {schemeInfo ? ` · Scheme: ${schemeInfo}` : ''}
          </p>
        </div>
      </div>

      <div className="panel" style={{ marginBottom: 12 }}>
        <div className="panel-header">Cause enrichment (field / asset)</div>
        <div className="panel-body">
          <p className="subtitle" style={{ marginTop: 0 }}>
            Physical causes (lightning, vegetation, cable…) stay inconclusive until you attach
            structured evidence — the engine will not invent them from waveforms alone.
          </p>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 10 }}>
            {(tagChoices.length
              ? tagChoices
              : [
                  { token: 'lightning_evidence', label: 'Lightning evidence' },
                  { token: 'field_report_vegetation', label: 'Vegetation (field)' },
                  { token: 'cable_asset_confirmed', label: 'Cable asset' },
                ]
            ).map((t) => (
              <label
                key={t.token}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: '0.82rem',
                  border: '1px solid var(--border)',
                  padding: '4px 8px',
                  borderRadius: 3,
                  cursor: 'pointer',
                  background: selected.has(t.token) ? 'var(--accent-soft)' : 'transparent',
                }}
              >
                <input
                  type="checkbox"
                  checked={selected.has(t.token)}
                  onChange={() => toggleTag(t.token)}
                />
                {t.label}
              </label>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-primary"
            disabled={enrichBusy}
            onClick={() => void saveCauseEvidence()}
          >
            {enrichBusy ? 'Saving…' : 'Save cause evidence'}
          </button>
          {enrichMsg && (
            <div className="alert alert-info" style={{ marginTop: 8 }}>
              {enrichMsg}{' '}
              {id && (
                <Link to={`/events/${id}/overview`}>Open Overview to re-run</Link>
              )}
            </div>
          )}
        </div>
      </div>

      {primary && (
        <div className="ux-strip">
          <div className="ux-item">
            <div className="ux-label">Why</div>
            <div className="ux-value">{primary.title}</div>
          </div>
          <div className="ux-item">
            <div className="ux-label">Confidence</div>
            <div className={`ux-value ${primary.confidence_level !== 'HIGH' ? 'uncertain' : ''}`}>
              {primary.confidence_level} ({((primary.confidence ?? 0) * 100).toFixed(0)}%)
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
                : '—'}
            </div>
          </div>
        </div>
      )}

      {primary && (
        <div className={`${styles.primary} panel`}>
          <div className="panel-header">
            <span>Primary hypothesis</span>
            <div className="badge-row">
              <span className="mono">{primary.hypothesis_code}</span>
              <StatusBadge status={primary.status} />
            </div>
          </div>
          <div className="panel-body">
            <h2 className={styles.title}>{primary.title}</h2>
            <p className={styles.statement}>{primary.statement}</p>
            {primary.explanation && (
              <p className={styles.explain}>{primary.explanation}</p>
            )}

            <div className={styles.columns}>
              <div>
                <h4>Supporting evidence</h4>
                <ul>
                  {(primary.supporting_evidence_ids ?? []).map((e) => (
                    <li key={e} className="mono">
                      {id ? <Link to={`/events/${id}/evidence`}>{e}</Link> : e}
                    </li>
                  ))}
                  {!primary.supporting_evidence_ids?.length && <li>—</li>}
                </ul>
              </div>
              <div>
                <h4>Contradicting</h4>
                <ul>
                  {(primary.contradicting_evidence_ids ?? []).map((e) => (
                    <li key={e} className="mono">
                      {e}
                    </li>
                  ))}
                  {!primary.contradicting_evidence_ids?.length && <li>None recorded</li>}
                </ul>
              </div>
              <div>
                <h4>Missing evidence</h4>
                <ul className={styles.missing}>
                  {(primary.missing_evidence ?? []).map((e) => (
                    <li key={e}>{humanizeEvidenceToken(e)}</li>
                  ))}
                  {!primary.missing_evidence?.length && <li>—</li>}
                </ul>
              </div>
            </div>

            {primary.causal_chain && (
              <div className={styles.chain}>
                <h4>Causal chain</h4>
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

      {alts.length > 0 && (
        <div className="panel" style={{ marginTop: 16 }}>
          <div className="panel-header">Alternative hypotheses</div>
          <div className="panel-body" style={{ padding: 0 }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Rank</th>
                  <th>Code</th>
                  <th>Title</th>
                  <th>Status</th>
                  <th>Confidence</th>
                  <th>Uncertainty notes</th>
                </tr>
              </thead>
              <tbody>
                {alts.map((h) => (
                  <tr key={h.id}>
                    <td className="num">{h.rank}</td>
                    <td className="mono">{h.hypothesis_code}</td>
                    <td>{h.title}</td>
                    <td>
                      <StatusBadge status={h.status} />
                    </td>
                    <td className="num">
                      {h.confidence_level} ({((h.confidence ?? 0) * 100).toFixed(0)}%)
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                      {h.missing_evidence?.join('; ') || h.explanation || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
