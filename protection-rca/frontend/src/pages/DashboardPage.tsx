import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import { api } from '@/services/api';
import { formatDrDate, parseApiDate } from '@/utils/dateTime';
import type { DashboardStats } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { SeverityBadge } from '@/components/SeverityBadge';
import { DataQualityBadge } from '@/components/DataQualityBadge';
import {
  getLastEvent,
  loadRecentEvents,
  syncRecentEvents,
  clearRecentEvents,
  recentEventLabel,
  recentEventDetail,
} from '@/utils/recentEvents';
import styles from './DashboardPage.module.css';

type TrendDays = 7 | 30 | 90;

const RCA_LABELS: Record<string, string> = {
  ANALYSIS_COMPLETE: 'Complete',
  ANALYSIS_COMPLETE_WITH_WARNINGS: 'Complete*',
  ENGINEER_REVIEW_REQUIRED: 'Review req',
  DATA_INSUFFICIENT: 'No data',
  INCONCLUSIVE: 'Inconclusive',
};

const STATUS_LABELS: Record<string, string> = {
  AWAITING_REVIEW: 'Review',
  REVIEW: 'Review',
  UPLOADED: 'Uploaded',
  ANALYZING: 'Analysing',
  CLOSED: 'Closed',
  FAILED: 'Failed',
};

const DQ_LABELS: Record<string, string> = {
  GOOD: 'Good',
  ACCEPTABLE: 'Acceptable',
  WARNING: 'Warning',
  POOR: 'Poor',
  INVALID: 'Invalid',
};

type TrendPoint = NonNullable<DashboardStats['trend_30d']>[number];

function dayTotal(p: TrendPoint): number {
  return Math.max(p.events ?? 0, p.analysed + p.review + p.issues);
}

function formatTrendDay(iso: string): string {
  const d = parseApiDate(iso);
  if (!d) return iso.slice(5);
  return format(d, 'd MMM');
}

/** Zoom to activity; if sparse, show only active days so bars stay readable. */
function prepareTrendPoints(points: TrendPoint[]): {
  visible: TrendPoint[];
  mode: 'timeline' | 'active';
} {
  if (!points.length) return { visible: [], mode: 'timeline' };
  const activeIdx = points
    .map((p, i) => (dayTotal(p) > 0 ? i : -1))
    .filter((i) => i >= 0);
  if (!activeIdx.length) return { visible: points, mode: 'timeline' };

  const density = activeIdx.length / points.length;
  // Few active days → categorical bars (avoid a lonely spike in empty space)
  if (activeIdx.length <= 10 || density <= 0.25) {
    return { visible: activeIdx.map((i) => points[i]), mode: 'active' };
  }

  const first = Math.max(0, activeIdx[0] - 1);
  const last = Math.min(points.length - 1, activeIdx[activeIdx.length - 1] + 1);
  return { visible: points.slice(first, last + 1), mode: 'timeline' };
}

function niceMax(raw: number): number {
  if (raw <= 1) return 1;
  if (raw <= 4) return 4;
  if (raw <= 8) return 8;
  const step = raw <= 20 ? 5 : raw <= 50 ? 10 : 20;
  return Math.ceil(raw / step) * step;
}

function TrendChart({ points }: { points: TrendPoint[] }) {
  const { visible, mode } = prepareTrendPoints(points);
  const width = 640;
  const height = 248;
  const pad = { t: 28, r: 16, b: 40, l: 40 };
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  const rawMax = Math.max(1, ...visible.map(dayTotal));
  const max = niceMax(rawMax);
  const n = Math.max(visible.length, 1);
  const slot = innerW / n;
  const barW =
    mode === 'active'
      ? Math.min(48, Math.max(18, slot * 0.55))
      : Math.min(22, Math.max(5, slot * 0.62));
  const labelEvery =
    mode === 'active'
      ? 1
      : visible.length > 45
        ? 7
        : visible.length > 20
          ? 4
          : visible.length > 10
            ? 2
            : 1;
  const showValues = mode === 'active' || visible.filter((p) => dayTotal(p) > 0).length <= 12;
  const yTicks = [0, 0.25, 0.5, 0.75, 1].map((f) => Math.round(max * f));
  const uniqueTicks = [...new Set(yTicks)];

  const total = visible.reduce((s, p) => s + dayTotal(p), 0);
  const peak = visible.reduce(
    (best, p) => (dayTotal(p) > dayTotal(best) ? p : best),
    visible[0],
  );
  const activeDays = visible.filter((p) => dayTotal(p) > 0).length;

  return (
    <div className={styles.trendBody}>
      <div className={styles.trendStats} aria-label="Trend summary">
        <div>
          <span className={styles.trendStatVal}>{total}</span>
          <span className={styles.trendStatLbl}>events in view</span>
        </div>
        <div>
          <span className={styles.trendStatVal}>{activeDays}</span>
          <span className={styles.trendStatLbl}>active day{activeDays === 1 ? '' : 's'}</span>
        </div>
        <div>
          <span className={styles.trendStatVal}>{dayTotal(peak)}</span>
          <span className={styles.trendStatLbl}>peak · {formatTrendDay(peak.date)}</span>
        </div>
      </div>

      <svg viewBox={`0 0 ${width} ${height}`} className={styles.chartSvg} role="img">
        <title>Event volume trend</title>
        <rect
          x={pad.l}
          y={pad.t}
          width={innerW}
          height={innerH}
          className={styles.plotBg}
          rx={6}
        />
        {uniqueTicks.map((tick) => {
          const y = pad.t + innerH * (1 - tick / max);
          return (
            <g key={tick}>
              <line
                x1={pad.l}
                x2={width - pad.r}
                y1={y}
                y2={y}
                className={tick === 0 ? styles.baseLine : styles.gridLine}
              />
              <text x={pad.l - 10} y={y + 3.5} className={styles.axisLabel} textAnchor="end">
                {tick}
              </text>
            </g>
          );
        })}
        <text
          x={14}
          y={pad.t + innerH / 2}
          className={styles.axisTitle}
          textAnchor="middle"
          transform={`rotate(-90 14 ${pad.t + innerH / 2})`}
        >
          Events / day
        </text>

        {visible.map((p, i) => {
          const totalDay = dayTotal(p);
          const x = pad.l + i * slot + (slot - barW) / 2;
          const a = (p.analysed / max) * innerH;
          const r = (p.review / max) * innerH;
          const iss = (p.issues / max) * innerH;
          let stacked = a + r + iss;
          // Keep stack consistent with day total when backend buckets one status per event
          if (stacked <= 0 && totalDay > 0) {
            stacked = (totalDay / max) * innerH;
          }
          let y = pad.t + innerH;
          const stacks =
            a + r + iss > 0
              ? [
                  { h: a, cls: styles.barAnalysed, key: 'a' },
                  { h: r, cls: styles.barReview, key: 'r' },
                  { h: iss, cls: styles.barIssues, key: 'i' },
                ]
              : totalDay > 0
                ? [{ h: (totalDay / max) * innerH, cls: styles.barEvents, key: 'e' }]
                : [];
          const tip = [
            formatTrendDay(p.date),
            `${totalDay} event${totalDay === 1 ? '' : 's'}`,
            p.analysed ? `${p.analysed} analysed` : '',
            p.review ? `${p.review} review` : '',
            p.issues ? `${p.issues} issues` : '',
          ]
            .filter(Boolean)
            .join(' · ');

          return (
            <g key={p.date}>
              {totalDay === 0 && mode === 'timeline' && (
                <line
                  x1={x + barW / 2}
                  x2={x + barW / 2}
                  y1={pad.t + innerH - 3}
                  y2={pad.t + innerH}
                  className={styles.zeroTick}
                />
              )}
              {stacks.map((s) => {
                if (s.h <= 0) return null;
                y -= s.h;
                const h = Math.max(s.h, totalDay > 0 ? 3 : 0);
                return (
                  <rect
                    key={s.key}
                    x={x}
                    y={y - (h - s.h)}
                    width={barW}
                    height={h}
                    className={s.cls}
                    rx={mode === 'active' ? 4 : 2}
                  >
                    <title>{tip}</title>
                  </rect>
                );
              })}
              {showValues && totalDay > 0 && (
                <text
                  x={x + barW / 2}
                  y={pad.t + innerH - stacked - 6}
                  className={styles.barValue}
                  textAnchor="middle"
                >
                  {totalDay}
                </text>
              )}
              {i % labelEvery === 0 && (
                <text
                  x={x + barW / 2}
                  y={height - 14}
                  className={styles.axisLabel}
                  textAnchor="middle"
                >
                  {formatTrendDay(p.date)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
      {mode === 'active' && points.length > visible.length && (
        <p className={styles.trendNote}>
          Showing {visible.length} day{visible.length === 1 ? '' : 's'} with activity
          (empty days hidden for clarity)
        </p>
      )}
    </div>
  );
}

function DqDonut({ dq }: { dq: NonNullable<DashboardStats['data_quality']> }) {
  const segments = [
    { key: 'good', value: dq.good, color: 'var(--dq-good)', label: 'Good' },
    {
      key: 'acceptable',
      value: dq.acceptable,
      color: 'var(--dq-acceptable)',
      label: 'Acceptable',
    },
    { key: 'warning', value: dq.warning, color: 'var(--dq-warning)', label: 'Warning' },
    { key: 'poor', value: dq.poor, color: 'var(--dq-poor)', label: 'Poor' },
    { key: 'invalid', value: dq.invalid, color: 'var(--dq-invalid)', label: 'Invalid' },
    {
      key: 'unsupported',
      value: dq.unsupported ?? 0,
      color: '#8b6bb0',
      label: 'Unsupported',
    },
    {
      key: 'not_validated',
      value: dq.not_validated ?? 0,
      color: 'var(--text-muted)',
      label: 'Not validated',
    },
    { key: 'unknown', value: dq.unknown, color: '#4a5568', label: 'Unknown' },
  ].filter((s) => s.value > 0);

  const total = segments.reduce((a, s) => a + s.value, 0) || 1;
  const goodPct = Math.round(((dq.good + dq.acceptable) / total) * 100);
  const r = 54;
  const c = 2 * Math.PI * r;
  let offset = 0;

  return (
    <div className={styles.donutWrap}>
      <svg viewBox="0 0 140 140" className={styles.donutSvg}>
        <circle cx="70" cy="70" r={r} className={styles.donutTrack} />
        {segments.map((s) => {
          const len = (s.value / total) * c;
          const el = (
            <circle
              key={s.key}
              cx="70"
              cy="70"
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth="14"
              strokeDasharray={`${len} ${c - len}`}
              strokeDashoffset={-offset}
              transform="rotate(-90 70 70)"
            />
          );
          offset += len;
          return el;
        })}
        <text x="70" y="64" textAnchor="middle" className={styles.donutPct}>
          {segments.length ? `${goodPct}%` : '—'}
        </text>
        <text x="70" y="82" textAnchor="middle" className={styles.donutSub}>
          overall
        </text>
      </svg>
      <ul className={styles.donutLegend}>
        {segments.length === 0 && <li className={styles.muted}>No quality data yet</li>}
        {segments.map((s) => (
          <li key={s.key}>
            <span className={styles.swatch} style={{ background: s.color }} />
            <span className={styles.legendName}>{s.label}</span>
            <strong>
              {s.value}
              <span className={styles.legendPct}>{Math.round((s.value / total) * 100)}%</span>
            </strong>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DashboardPage() {
  const navigate = useNavigate();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState<TrendDays>(30);
  const [lastLocal, setLastLocal] = useState(() => getLastEvent());
  const [recentLocal, setRecentLocal] = useState(() => loadRecentEvents().slice(0, 5));

  useEffect(() => {
    let cancelled = false;

    const load = (showSpinner: boolean) => {
      if (showSpinner) setLoading(true);
      void api
        .getDashboardStats(days)
        .then(async (s) => {
          if (cancelled) return;
          setStats(s);
          setError(null);
          if ((s.total_events ?? 0) === 0) {
            clearRecentEvents();
            setLastLocal(null);
            setRecentLocal([]);
            return;
          }
          try {
            const all = await api.getEvents();
            if (cancelled) return;
            const synced = syncRecentEvents(all);
            setLastLocal(synced[0] ?? null);
            setRecentLocal(synced.slice(0, 5));
          } catch {
            if (cancelled) return;
            setLastLocal(getLastEvent());
            setRecentLocal(loadRecentEvents().slice(0, 5));
          }
        })
        .catch((e: Error) => {
          if (!cancelled) setError(e.message || 'Failed to load dashboard');
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    };

    load(true);

    // Keep KPIs in sync after events are created/deleted elsewhere in the app.
    const onVisible = () => {
      if (document.visibilityState === 'visible') load(false);
    };
    const onFocus = () => load(false);
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('focus', onFocus);
    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('focus', onFocus);
    };
  }, [days]);

  const openQueue = (queue?: string) => {
    navigate(queue ? `/events?queue=${encodeURIComponent(queue)}` : '/events');
  };

  const opsKpis = useMemo(() => {
    if (!stats) return [];
    const tone = (value: number, active: 'warn' | 'danger' | 'ok' | 'info', zero: 'info' = 'info') =>
      value > 0 ? active : zero;
    return [
      {
        label: 'Total events',
        value: stats.total_events,
        cls: 'info' as const,
        hint: 'All recorded disturbances',
        queue: undefined as string | undefined,
      },
      {
        label: 'Awaiting analysis',
        value: stats.awaiting_analysis,
        cls: tone(stats.awaiting_analysis, 'warn'),
        hint: 'Uploaded / queued for analysis',
        queue: 'awaiting_analysis',
      },
      {
        label: 'Awaiting review',
        value: stats.awaiting_review,
        cls: tone(stats.awaiting_review, 'warn'),
        hint: 'Engineer disposition needed',
        queue: 'awaiting_review',
      },
      {
        label: 'Events with reports',
        value: stats.completed_reports,
        cls: tone(stats.completed_reports, 'ok', 'info'),
        hint: 'Live count — rises with new reports, drops when events are deleted',
        queue: 'completed_reports',
      },
    ];
  }, [stats]);

  /** Quality health — problem counters; zero means that check type is clear. */
  const qualityCards = useMemo(() => {
    if (!stats) return [];
    return [
      {
        label: 'Protection consistency',
        value: stats.consistency_issues,
        clsActive: 'danger' as const,
        clearText: 'Clear',
        clearHint: 'No mismatched operate / setting checks',
        issueHint: 'Events with inconsistent protection behaviour',
        queue: 'consistency_issues',
      },
      {
        label: 'High / critical findings',
        value: stats.high_severity_findings,
        clsActive: 'danger' as const,
        clearText: 'None',
        clearHint: 'No HIGH or CRITICAL findings open',
        issueHint: 'Findings rated HIGH or CRITICAL',
        queue: 'high_severity',
      },
      {
        label: 'RCA not confirmed',
        value: stats.rca_inconclusive,
        clsActive: 'warn' as const,
        clearText: 'Clear',
        clearHint: 'Primary root cause ranked for analysed events',
        issueHint: 'Inconclusive RCA — needs evidence or settings',
        queue: 'rca_inconclusive',
      },
      {
        label: 'Record data quality',
        value: stats.parser_dq_issues,
        clsActive: 'danger' as const,
        clearText: 'Good',
        clearHint: 'No WARNING / POOR / INVALID COMTRADE records',
        issueHint: 'Records with WARNING, POOR or INVALID quality',
        queue: 'parser_dq_issues',
      },
    ];
  }, [stats]);

  const trend = stats?.trend_30d ?? [];
  const dq = stats?.data_quality ?? {
    good: 0,
    acceptable: 0,
    warning: 0,
    poor: 0,
    invalid: 0,
    unknown: 0,
    not_validated: 0,
    unsupported: 0,
  };
  const attention = stats?.attention ?? [];
  const recent = stats?.recent_events ?? [];
  const empty = !loading && (stats?.total_events ?? 0) === 0;
  const inboxNeed =
    (stats?.awaiting_review ?? 0) +
    (stats?.awaiting_analysis ?? 0) +
    (stats?.consistency_issues ?? 0) +
    (stats?.high_severity_findings ?? 0);
  const qualityIssueTotal = qualityCards.reduce((s, c) => s + c.value, 0);
  const qualityAllClear = !loading && !empty && qualityIssueTotal === 0;

  const renderKpi = (k: (typeof opsKpis)[number]) => (
    <button
      key={k.label}
      type="button"
      className={`kpi-card ${k.cls} ${styles.kpiClick}`}
      onClick={() => openQueue(k.queue)}
      title={`Open ${k.label}`}
    >
      <div className="kpi-label">{k.label}</div>
      <div className="kpi-value">{loading ? '…' : k.value}</div>
      <div className="kpi-hint">{k.hint}</div>
    </button>
  );

  const renderQualityCard = (k: (typeof qualityCards)[number]) => {
    const clear = k.value === 0;
    const cls = clear ? 'ok' : k.clsActive;
    return (
      <button
        key={k.label}
        type="button"
        className={`kpi-card ${cls} ${styles.kpiClick}`}
        onClick={() => openQueue(k.queue)}
        title={clear ? k.clearHint : `Open ${k.value} event(s): ${k.issueHint}`}
      >
        <div className="kpi-label">{k.label}</div>
        <div className="kpi-value">
          {loading ? '…' : clear ? k.clearText : k.value}
        </div>
        <div className="kpi-hint">{clear ? k.clearHint : k.issueHint}</div>
      </button>
    );
  };

  const queueChips = [
    { label: 'Analyse', value: stats?.awaiting_analysis ?? 0, queue: 'awaiting_analysis' },
    { label: 'Review', value: stats?.awaiting_review ?? 0, queue: 'awaiting_review' },
    { label: 'Consistency', value: stats?.consistency_issues ?? 0, queue: 'consistency_issues' },
    { label: 'High severity', value: stats?.high_severity_findings ?? 0, queue: 'high_severity' },
  ];

  const formatConsistency = (raw: string) => {
    if (!raw || raw === '—' || raw === 'N/A') return '—';
    if (/^0\b/i.test(raw) || /^consistent$/i.test(raw)) return 'Consistent';
    if (/findings?/i.test(raw)) return raw.replace(/findings?/i, (m) => m.toLowerCase());
    return raw;
  };

  return (
    <div className={`page ${styles.dash}`}>
      <div className="page-header">
        <div>
          <h1>Operations dashboard</h1>
          <p className="subtitle">Triage inbox, quality, and recent disturbance events</p>
        </div>
        <div className={styles.headerActions}>
          {lastLocal && (
            <Link
              to={`/events/${lastLocal.id}/summary`}
              className="btn btn-primary"
              title={recentEventDetail(lastLocal)}
            >
              Continue {recentEventLabel(lastLocal)}
            </Link>
          )}
          <Link to="/events" className="btn">
            All events
          </Link>
          <Link to="/plant" className="btn">
            Plant
          </Link>
        </div>
      </div>

      {!empty && !loading && (
        <div className={styles.inboxHero}>
          <div className={styles.inboxMain}>
            <div className={styles.inboxLabel}>Work inbox</div>
            <div className={styles.inboxLine}>
              {inboxNeed === 0 ? (
                <>
                  <strong className={styles.inboxClear}>Clear</strong>
                  <span className={styles.inboxMuted}> — no items need attention</span>
                </>
              ) : (
                <>
                  <strong>{inboxNeed}</strong>
                  <span className={styles.inboxMuted}>
                    {' '}
                    item{inboxNeed === 1 ? '' : 's'} need attention
                  </span>
                </>
              )}
            </div>
            <div className={styles.queueChips} aria-label="Queue breakdown">
              {queueChips.map((q) => (
                <button
                  key={q.queue}
                  type="button"
                  className={`${styles.queueChip} ${q.value > 0 ? styles.queueChipHot : ''}`}
                  onClick={() => openQueue(q.queue)}
                >
                  <span className={styles.queueChipVal}>{q.value}</span>
                  <span className={styles.queueChipLbl}>{q.label}</span>
                </button>
              ))}
            </div>
            {recentLocal.length > 0 && (
              <div className={styles.recentRow}>
                <span className={styles.recentLabel}>Recent</span>
                {recentLocal.map((r) => (
                  <Link
                    key={r.id}
                    to={`/events/${r.id}/summary`}
                    className={styles.recentLink}
                    title={recentEventDetail(r)}
                  >
                    {recentEventLabel(r)}
                    {r.feeder ? (
                      <span className={styles.recentMeta}>{r.feeder}</span>
                    ) : null}
                  </Link>
                ))}
              </div>
            )}
          </div>
          <div className={styles.inboxActions}>
            <button
              type="button"
              className="btn btn-sm btn-primary"
              onClick={() => openQueue('awaiting_review')}
              disabled={(stats?.awaiting_review ?? 0) === 0}
            >
              Open review queue
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => openQueue('awaiting_analysis')}
              disabled={(stats?.awaiting_analysis ?? 0) === 0}
            >
              Open analyse queue
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="alert alert-error" role="alert">
          {error}
        </div>
      )}

      {empty && (
        <div className={styles.emptyBanner}>
          <div>
            <strong>No disturbance events yet</strong>
            <p>
              Start by creating an event and uploading a disturbance record package. No demo
              data is seeded.
            </p>
            <ol className={styles.workflowList}>
              <li>Build Plant (SS → kV → Bay → Feeder → IED)</li>
              <li>Upload records on IED</li>
              <li>Validate COMTRADE</li>
              <li>Run Analysis</li>
              <li>Review Consistency</li>
              <li>Review RCA</li>
              <li>Generate Report</li>
            </ol>
          </div>
          <div className={styles.emptyActions}>
            <Link to="/plant" className="btn btn-primary">
              Open Plant
            </Link>
          </div>
        </div>
      )}

      <div className={styles.kpiStrip}>
        <section aria-label="Operations metrics">
          <h2 className={styles.kpiSectionTitle}>Operations</h2>
          <div className={styles.kpiGrid}>{opsKpis.map(renderKpi)}</div>
        </section>
        <section aria-label="Quality health" className={styles.qualitySection}>
          <div className={styles.qualityHead}>
            <div>
              <h2 className={styles.kpiSectionTitle}>Quality health</h2>
              <p className={styles.sectionIntro}>
                Open issues from analysed events — consistency mismatches, severe findings,
                inconclusive RCA, and poor COMTRADE quality.
              </p>
            </div>
            {!loading && !empty && (
              <div
                className={`${styles.healthPill} ${qualityAllClear ? styles.healthPillOk : styles.healthPillWarn}`}
              >
                {qualityAllClear
                  ? 'All clear'
                  : `${qualityIssueTotal} open issue${qualityIssueTotal === 1 ? '' : 's'}`}
              </div>
            )}
          </div>
          <div className={styles.kpiGrid}>{qualityCards.map(renderQualityCard)}</div>
        </section>
      </div>

      <div className={styles.midGrid}>
        <section className={`panel ${styles.trendPanel}`}>
          <div className="panel-header">
            <span>Event trend</span>
            <div className={styles.trendControls}>
              {([7, 30, 90] as TrendDays[]).map((d) => (
                <button
                  key={d}
                  type="button"
                  className={`${styles.dayBtn} ${days === d ? styles.dayActive : ''}`}
                  onClick={() => setDays(d)}
                >
                  {d}d
                </button>
              ))}
            </div>
            <div className={styles.legendInline}>
              <span>
                <i className={styles.lgAnalysed} /> Analysed
              </span>
              <span>
                <i className={styles.lgReview} /> Review
              </span>
              <span>
                <i className={styles.lgIssues} /> Issues
              </span>
            </div>
          </div>
          <div className={`panel-body ${styles.trendPanelBody}`}>
            {trend.length === 0 ||
            trend.every(
              (p) => (p.events ?? 0) + p.analysed + p.review + p.issues === 0,
            ) ? (
              <div className={styles.chartEmpty}>No events in the selected window</div>
            ) : (
              <TrendChart points={trend} />
            )}
          </div>
        </section>

        <div className={styles.sideStack}>
          <section className={`panel ${styles.attentionPanel}`}>
            <div className="panel-header">
              <span>Attention required</span>
              <span className={styles.badgeCount}>{attention.length}</span>
            </div>
            <div className="panel-body" style={{ padding: 0 }}>
              {attention.length === 0 ? (
                <div className={styles.chartEmpty}>Queue clear — nothing urgent</div>
              ) : (
                <ul className={styles.attentionList}>
                  {attention.map((a, idx) => (
                    <li key={`${a.id}-${idx}`}>
                      <Link to={`/events/${a.id}/overview`} className={styles.attId}>
                        {a.event_id}
                      </Link>
                      <span className={styles.attReason}>{a.reason}</span>
                      <SeverityBadge
                        severity={
                          a.severity as 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
                        }
                      />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <section className={`panel ${styles.dqPanel}`}>
            <div className="panel-header">
              <span>Data quality</span>
            </div>
            <div className="panel-body">
              <DqDonut dq={dq} />
            </div>
          </section>
        </div>
      </div>

      <section className="panel">
        <div className="panel-header">
          <span>Recent events</span>
          <Link to="/events">View all</Link>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <div className={styles.tableScroll}>
            <table className={`data-table ${styles.recentTable}`}>
              <thead>
                <tr>
                  <th>Event ID</th>
                  <th title="Relay disturbance / COMTRADE trigger time">DR time</th>
                  <th title="When this event was created in Protection Expert System">Created</th>
                  <th>Substation / Bay</th>
                  <th>Relay</th>
                  <th>Fault</th>
                  <th>Protection</th>
                  <th>Consistency</th>
                  <th>RCA</th>
                  <th>Status</th>
                  <th>Severity</th>
                  <th>DQ</th>
                </tr>
              </thead>
              <tbody>
                {recent.length === 0 && (
                  <tr>
                    <td colSpan={12} className={styles.chartEmpty}>
                      No disturbance events yet. Create your first event by uploading a
                      disturbance package.
                    </td>
                  </tr>
                )}
                {recent.map((ev) => (
                  <tr key={ev.id}>
                    <td>
                      <Link to={`/events/${ev.id}/overview`} className="mono">
                        {ev.event_id}
                      </Link>
                    </td>
                    <td className="num" title="Relay disturbance / COMTRADE trigger time">
                      {(() => {
                        const s = formatDrDate(ev.event_datetime, '');
                        if (!s) return '—';
                        const m = s.match(/^(\d{2})\/(\d{2})\/(\d{4}),\s*(\d{2}:\d{2}:\d{2})/);
                        return m ? `${m[3]}-${m[2]}-${m[1]} ${m[4].slice(0, 5)}` : s;
                      })()}
                    </td>
                    <td className="num" title="Created in this application">
                      {(() => {
                        const d = parseApiDate(ev.created_at);
                        return d ? format(d, 'yyyy-MM-dd HH:mm') : '—';
                      })()}
                    </td>
                    <td>{ev.location}</td>
                    <td className="mono">{ev.relay}</td>
                    <td className="mono">{ev.fault_type ?? '—'}</td>
                    <td className="mono">{ev.protection_summary}</td>
                    <td>
                      <span
                        className={
                          /findings?/i.test(ev.consistency_summary) &&
                          !/^0\b/i.test(ev.consistency_summary) &&
                          !/^consistent$/i.test(ev.consistency_summary)
                            ? styles.consBad
                            : styles.consOk
                        }
                      >
                        {formatConsistency(ev.consistency_summary)}
                      </span>
                    </td>
                    <td>
                      <StatusBadge
                        status={ev.rca_status}
                        label={RCA_LABELS[ev.rca_status] ?? ev.rca_status.replace(/_/g, ' ')}
                      />
                    </td>
                    <td>
                      <StatusBadge
                        status={ev.status}
                        label={STATUS_LABELS[ev.status] ?? ev.status.replace(/_/g, ' ')}
                      />
                    </td>
                    <td>
                      {ev.severity ? (
                        <SeverityBadge
                          severity={
                            ev.severity as 'INFO' | 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
                          }
                        />
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      {ev.data_quality ? (
                        <DataQualityBadge
                          quality={
                            ev.data_quality as
                              | 'GOOD'
                              | 'ACCEPTABLE'
                              | 'WARNING'
                              | 'POOR'
                              | 'INVALID'
                          }
                          label={DQ_LABELS[ev.data_quality] ?? ev.data_quality}
                        />
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {recent.length === 0 && (
            <div className={styles.emptyActions} style={{ padding: 16 }}>
              <Link to="/plant" className="btn btn-primary">
                Open Plant
              </Link>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
