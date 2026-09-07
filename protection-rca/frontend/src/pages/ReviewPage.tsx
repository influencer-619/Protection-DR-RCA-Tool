import { useState, type FormEvent } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { ReviewAction } from '@/types';

const ACTIONS: { value: ReviewAction; label: string; hint: string }[] = [
  { value: 'ACCEPT', label: 'ACCEPT', hint: 'Accept analysis findings as-is' },
  { value: 'MODIFY', label: 'MODIFY', hint: 'Accept with engineer corrections' },
  { value: 'REJECT', label: 'REJECT', hint: 'Reject automated conclusions' },
  { value: 'INCONCLUSIVE', label: 'INCONCLUSIVE', hint: 'Insufficient certainty to close' },
  {
    value: 'REQUEST_FIELD_INVESTIGATION',
    label: 'REQUEST FIELD INVESTIGATION',
    hint: 'Dispatch field / patrol verification',
  },
];

export function ReviewPage() {
  const { id } = useParams<{ id: string }>();
  const [action, setAction] = useState<ReviewAction>('ACCEPT');
  const [comments, setComments] = useState('');
  const [modifications, setModifications] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!id) return;
    setSaving(true);
    try {
      await api.submitReview(id, {
        action,
        comments,
        modifications: modifications
          ? { notes: modifications }
          : undefined,
      });
      setSubmitted(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      <div className="page-header" style={{ padding: 0, marginBottom: 16 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Engineer review</h1>
          <p className="subtitle">
            Disposition of automated analysis — What / Why / Setting / Evidence / Uncertainty
          </p>
        </div>
      </div>

      {submitted && (
        <div className="alert alert-ok" role="status">
          Review recorded: <strong className="mono">{action}</strong>
        </div>
      )}

      <form onSubmit={onSubmit} className="panel">
        <div className="panel-header">Review action</div>
        <div className="panel-body">
          <div className="stack-sm" style={{ marginBottom: 16 }}>
            {ACTIONS.map((a) => (
              <label
                key={a.value}
                style={{
                  display: 'flex',
                  gap: 10,
                  alignItems: 'flex-start',
                  padding: '10px 12px',
                  border: `1px solid ${action === a.value ? 'var(--accent)' : 'var(--border)'}`,
                  borderRadius: 'var(--radius)',
                  background: action === a.value ? 'var(--accent-soft)' : 'var(--bg-elevated)',
                  cursor: 'pointer',
                }}
              >
                <input
                  type="radio"
                  name="action"
                  value={a.value}
                  checked={action === a.value}
                  onChange={() => setAction(a.value)}
                  style={{ marginTop: 3 }}
                />
                <span>
                  <span className="mono" style={{ fontWeight: 600 }}>
                    {a.label}
                  </span>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{a.hint}</div>
                </span>
              </label>
            ))}
          </div>

          {(action === 'MODIFY' || action === 'REJECT') && (
            <div className="form-group">
              <label htmlFor="modifications">Modifications / corrections</label>
              <textarea
                id="modifications"
                className="form-control"
                rows={3}
                value={modifications}
                onChange={(e) => setModifications(e.target.value)}
                placeholder="Corrected fault type, hypothesis rank, setting notes…"
              />
            </div>
          )}

          <div className="form-group">
            <label htmlFor="comments">Comments</label>
            <textarea
              id="comments"
              className="form-control"
              rows={4}
              value={comments}
              onChange={(e) => setComments(e.target.value)}
              placeholder="Engineering rationale, residual uncertainty, field actions…"
              required
            />
          </div>

          <button type="submit" className="btn btn-primary" disabled={saving}>
            {saving ? 'Submitting…' : 'Submit review'}
          </button>
        </div>
      </form>
    </div>
  );
}
