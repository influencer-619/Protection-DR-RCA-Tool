import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api, apiClient, getStoredToken } from '@/services/api';
import type { Report } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState } from '@/components/EmptyState';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import styles from './ReportPage.module.css';

type ReviewRow = {
  action?: string;
  comments?: string | null;
  decision_state?: string | null;
  reviewed_at?: string | null;
};

function reportHtml(report: Report | null): string {
  if (!report) return '';
  const sections = report.sections as
    | { html_content?: string; html_preview?: string }
    | undefined;
  return (
    report.html_content ||
    sections?.html_content ||
    sections?.html_preview ||
    ''
  );
}

function toPct(n: number): string {
  const pct = n <= 1 ? n * 100 : n;
  return Number.isInteger(pct) ? `${pct}%` : `${pct.toFixed(1)}%`;
}

/** Convert decimal RCA scores in report HTML to percentages. */
function patchScoresToPercent(html: string): string {
  if (!html) return html;
  // Match "(score 0.7975)" → "(score 79.8%)"
  let out = html.replace(/(\(score\s+)(0\.\d+)(\))/gi, (_m, a: string, num: string, c: string) => {
    return `${a}${toPct(parseFloat(num))}${c}`;
  });
  // Also match "score 0.7975" without requiring parens around the whole phrase
  out = out.replace(/\b(score\s+)(0\.\d+)\b/gi, (_m, a: string, num: string) => {
    return `${a}${toPct(parseFloat(num))}`;
  });
  // RCA Assessment table only (section 13 → 14)
  out = out.replace(
    /(13\.\s*RCA Assessment[\s\S]*?)(?=<h2>\s*14\.|$)/i,
    (section) =>
      section.replace(/<td>\s*(0\.\d+)\s*<\/td>/gi, (_m, num: string) => {
        return `<td>${toPct(parseFloat(num))}</td>`;
      }),
  );
  return out;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** Replace Engineer Review section when a disposition exists in the API. */
function patchEngineerReview(html: string, review: ReviewRow | null): string {
  if (!html || !review?.action) return html;
  const action = String(review.action).toUpperCase();
  if (action === 'PENDING') return html;
  const lines = [action];
  if (review.reviewed_at) lines.push(`Reviewed at: ${review.reviewed_at}`);
  if (review.decision_state) lines.push(`Decision state: ${review.decision_state}`);
  if (review.comments) lines.push(`Comments: ${review.comments}`);
  const block = `<pre style="white-space: pre-wrap; font-family: inherit; margin: 0;">${escapeHtml(
    lines.join('\n'),
  )}</pre>`;
  if (/19\.\s*Engineer Review/i.test(html)) {
    return html.replace(
      /(<h2>\s*19\.\s*Engineer Review\s*<\/h2>)([\s\S]*?)(?=<h2\b|<\/body>|$)/i,
      `$1\n  ${block}\n  `,
    );
  }
  // Fallback report without section 19 — append it
  return html.replace(
    /<\/body>/i,
    `<h2>19. Engineer Review</h2>\n${block}\n</body>`,
  );
}

function looksSparse(html: string): boolean {
  if (!html || html.length < 500) return true;
  if (
    html.includes('<h2>1. Executive Summary</h2>') &&
    html.includes('<h2>Fault</h2>') &&
    !html.includes('19. Engineer Review') &&
    !html.includes('Event Identification') &&
    !html.includes('2. Event Information')
  ) {
    return true;
  }
  return (
    html.includes('re-run analysis to reconstruct') ||
    html.includes('NOT AVAILABLE — set relay') ||
    html.includes('NOT AVAILABLE — re-run analysis after settings') ||
    (html.includes('Decision: NOT AVAILABLE') && html.includes('COMTRADE Data Quality'))
  );
}

async function fetchLatestReview(eventId: string): Promise<ReviewRow | null> {
  try {
    const { data } = await apiClient.get(`/review/event/${eventId}`);
    const items = Array.isArray(data) ? data : (data as { items?: ReviewRow[] })?.items;
    if (!Array.isArray(items) || !items.length) return null;
    return items[0] ?? null;
  } catch {
    return null;
  }
}

function applyDisplayPatches(html: string, review: ReviewRow | null): string {
  return patchEngineerReview(patchScoresToPercent(html), review);
}

export function ReportPage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision, event } = useEventOrWorkspace(id);
  const [report, setReport] = useState<Report | null>(null);
  const [displayHtml, setDisplayHtml] = useState('');
  const [busy, setBusy] = useState(false);
  const [genError, setGenError] = useState<string | null>(null);

  const loadFresh = async (forceRegen = false) => {
    if (!id) return;
    setBusy(true);
    setGenError(null);
    try {
      let r: Report | null = null;
      try {
        r = await api.getReport(id);
      } catch {
        r = null;
      }
      let html = reportHtml(r);
      const review = await fetchLatestReview(id);

      // Only regenerate when report is missing/broken — avoid overwriting with a
      // stale backend process. Scores + review are patched client-side below.
      if (forceRegen || !r || looksSparse(html)) {
        await apiClient.post('/reports', {
          event_id: id,
          report_type: 'RCA',
          format: 'HTML',
        });
        r = await api.getReport(id);
        html = reportHtml(r);
      }

      setReport(r);
      setDisplayHtml(applyDisplayPatches(html, review));
    } catch (e) {
      setGenError(
        e instanceof Error ? e.message : 'Could not generate report — run analysis first',
      );
      setReport(null);
      setDisplayHtml('');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    void loadFresh(analysisRevision > 0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, analysisRevision, event?.status]);

  const generate = async () => {
    await loadFresh(true);
  };

  const download = async (fmt: 'PDF' | 'HTML') => {
    if (!id) return;
    setBusy(true);
    try {
      if (fmt === 'HTML') {
        await apiClient.post('/reports', {
          event_id: id,
          report_type: report?.report_type || 'RCA',
          format: 'HTML',
        });
        const list = await apiClient.get<{ items: Report[] }>(`/reports/by-event/${id}`);
        const latest = list.data.items?.[0];
        if (!latest) return;
        const review = await fetchLatestReview(id);
        const patched = applyDisplayPatches(reportHtml(latest), review);
        const blob = new Blob([patched], { type: 'text/html;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${report?.title || 'report'}.html`;
        a.click();
        URL.revokeObjectURL(url);
        setReport(latest);
        setDisplayHtml(patched);
        return;
      }

      // PDF: regenerate from same HTML the UI shows (patched), then convert on server
      await apiClient.post('/reports', {
        event_id: id,
        report_type: report?.report_type || 'RCA',
        format: 'PDF',
      });
      const list = await apiClient.get<{ items: Report[] }>(`/reports/by-event/${id}`);
      const latest = list.data.items?.[0];
      if (!latest) return;
      const token = getStoredToken();
      const res = await fetch(
        `${apiClient.defaults.baseURL}/reports/${latest.id}/download`,
        { headers: token ? { Authorization: `Bearer ${token}` } : {} },
      );
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${report?.title || 'report'}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      setReport(latest);
    } finally {
      setBusy(false);
    }
  };

  if (!report && !busy) {
    return (
      <>
        {genError && (
          <div className="alert alert-error" role="alert">
            {genError}
          </div>
        )}
        <EmptyState
          title="No report yet"
          description="Disturbance / RCA reports are generated from completed analysis results. Contents only include evidence the pipeline produced — nothing is invented."
          tips={[
            'Run analysis until Consistency and RCA tabs have data',
            'Then generate a report here or finish disposition on Review',
          ]}
          actions={[
            {
              label: busy ? 'Generating…' : 'Generate report',
              primary: true,
              disabled: busy,
              onClick: () => void generate(),
            },
            { label: 'Open Review', to: id ? `/events/${id}/review` : '/events' },
            { label: 'Open Overview', to: id ? `/events/${id}/overview` : '/events' },
          ]}
        />
      </>
    );
  }

  if (busy && !report) {
    return <div className="empty-state">Building report from analysis results…</div>;
  }

  const html =
    displayHtml ||
    reportHtml(report) ||
    `<pre>${JSON.stringify(report?.sections ?? {}, null, 2)}</pre>`;

  return (
    <div>
      <div className="page-header" style={{ padding: 0, marginBottom: 16 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>{report?.title}</h1>
          <p className="subtitle">
            {report?.report_type} · {report?.format ?? 'JSON'} · Generated{' '}
            {report?.generated_at ?? '—'}
          </p>
        </div>
        <div className="badge-row">
          {report?.status && <StatusBadge status={report.status} />}
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={busy}
            onClick={() => void generate()}
          >
            {busy ? 'Refreshing…' : 'Refresh report'}
          </button>
          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void download('HTML')}>
            Download HTML
          </button>
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={busy}
            onClick={() => void download('PDF')}
          >
            Download PDF
          </button>
          <button type="button" className="btn btn-sm" onClick={() => window.print()}>
            Print
          </button>
        </div>
      </div>

      {genError && (
        <div className="alert alert-error" role="alert">
          {genError}
        </div>
      )}

      {report?.summary && <div className="alert alert-info">{report.summary}</div>}

      <div className={styles.report} dangerouslySetInnerHTML={{ __html: html }} />
    </div>
  );
}
