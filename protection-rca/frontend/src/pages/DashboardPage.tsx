import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { format, parseISO } from 'date-fns';
import { api } from '@/services/api';
import type { DashboardStats } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { SeverityBadge } from '@/components/SeverityBadge';
import { DataQualityBadge } from '@/components/DataQualityBadge';
import { getLastEvent, loadRecentEvents } from '@/utils/recentEvents';
import styles from './DashboardPage.module.css';

type TrendDays = 7 | 30 | 90;

function TrendChart({
  points,
}: {
  points: NonNullable<DashboardStats['trend_30d']>;
}) {
  const width = 560;
  const height = 180;
  const pad = { t: 16, r: 12, b: 28, l: 28 };
  const innerW = width - pad.l - pad.r;
  const innerH = height - pad.t - pad.b;
  const max = Math.max(
    1,
    ...points.map((p) => Math.max(p.events ?? 0, p.analysed + p.review + p.issues)),
  );
  const n = Math.max(points.length, 1);
  const gap = 2;
  const barW = Math.max(3, innerW / n - gap);
  const labelEvery = points.length > 60 ? 14 : points.length > 20 ? 5 : 1;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className={styles.chartSvg} role="img">
      <title>Event volume trend</title>
      {[0.25, 0.5, 0.75, 1].map((f) => {
        const y = pad.t + innerH * (1 - f);
        return (
          <g key={f}>
            <line
              x1={pad.l}
              x2={width - pad.r}
              y1={y}
              y2={y}
              className={styles.gridLine}
            />
            <text x={pad.l - 6} y={y + 3} className={styles.axisLabel} textAnchor="end">
              {Math.round(max * f)}
            </text>
          </g>
        );
      })}
      {points.map((p, i) => {
        const x = pad.l + i * (barW + gap);
        const a = (p.analysed / max) * innerH;
        const r = (p.review / max) * innerH;
        const iss = (p.issues / max) * innerH;
        let y = pad.t + innerH;
        const stacks = [
          { h: a, cls: styles.barAnalysed },
          { h: r, cls: styles.barReview },
          { h: iss, cls: styles.barIssues },
        ];
        return (
          <g key={p.date}>
            {stacks.map((s, si) => {
              y -= s.h;
              if (s.h <= 0) return null;
              return (
                <rect
                  key={si}
                  x={x}
                  y={y}
                  width={barW}
                  height={s.h}
                  className={s.cls}
                  rx={1}
                />
              );
            })}
            {i % labelEvery === 0 && (
              <text
                x={x + barW / 2}
                y={height - 8}
                className={styles.axisLabel}
                textAnchor="middle"
              >
                {p.date.slice(5)}
              </text>
            )}
          </g>
        );
      })}
    </svg>
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
        <text x="70" y="66" textAnchor="middle" className={styles.donutPct}>
          {segments.length ? `${goodPct}%` : '—'}
        </text>
        <text x="70" y="84" textAnchor="middle" className={styles.donutSub}>
          good+ok
        </text>
      </svg>
      <ul className={styles.donutLegend}>
        {segments.length === 0 && <li className={styles.muted}>No quality data yet</li>}
        {segments.map((s) => (
          <li key={s.key}>
            <span className={styles.swatch} style={{ background: s.color }} />
            {s.label}
            <strong>
              {s.value} · {Math.round((s.value / total) * 100)}%
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

  useEffect(() => {
    setLoading(true);
    void api
      .getDashboardStats(days)
      .then((s) => {
        setStats(s);
        setError(null);
      })
      .catch((e: Error) => setError(e.message || 'Failed to load dashboard'))
      .finally(() => setLoading(false));
  }, [days]);

  const openQueue = (queue?: string) => {
    navigate(queue ? `/events?queue=${encodeURIComponent(queue)}` : '/events');
  };

  const kpis = useMemo(() => {
    if (!stats) return [];
    return [
      {
        label: 'Total Events',
        value: stats.total_events,
        cls: 'info',
        hint: 'All recorded disturbances',
        queue: undefined as string | undefined,
      },
      {
        label: 'Awaiting Analysis',
        value: stats.awaiting_analysis,
        cls: 'warn',
        hint: 'Uploaded / queued',
        queue: 'awaiting_analysis',
      },
      {
        label: 'Awaiting Review',
        value: stats.awaiting_review,
        cls: 'warn',
        hint: 'Engineer disposition',
        queue: 'awaiting_review',
      },
      {
        label: 'Completed Reports',
        value: stats.completed_reports,
        cls: 'ok',
        hint: 'Generated reports',
        queue: 'completed_reports',
      },
      {
        label: 'Consistency Issues',
        value: stats.consistency_issues,
        cls: 'danger',
        hint: 'INCONSISTENT findings',
        queue: 'consistency_issues',
      },
      {
        label: 'High Severity Findings',
        value: stats.high_severity_findings,
        cls: 'danger',
        hint: 'HIGH / CRITICAL',
        queue: 'high_severity',
      },
      {
        label: 'RCA Inconclusive',
        value: stats.rca_inconclusive,
        cls: 'warn',
        hint: 'Needs evidence / settings',
        queue: 'rca_inconclusive',
      },
      {
        label: 'Parser / DQ Issues',
        value: stats.parser_dq_issues,
        cls: 'danger',
        hint: 'WARNING / POOR / INVALID',
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
  const lastLocal = getLastEvent();
  const recentLocal = loadRecentEvents().slice(0, 5);
  const inboxNeed =
    (stats?.awaiting_review ?? 0) +
    (stats?.awaiting_analysis ?? 0) +
    (stats?.consistency_issues ?? 0) +
    (stats?.high_severity_findings ?? 0);

  return (
    <div className={`page ${styles.dash}`}>
      <div className="page-header">
        <div>
          <h1>Operations dashboard</h1>
          <p className="subtitle">
            Today&apos;s inbox · continue last event · consistency · RCA
          </p>
        </div>
        <div className={styles.headerActions}>
          {lastLocal && (
            <Link
              to={`/events/${lastLocal.id}/summary`}
              className="btn btn-primary"
              title={lastLocal.event_id}
            >
              Continue {lastLocal.event_id}
            </Link>
          )}
          <Link to="/events/compare" className="btn">
            Compare
          </Link>
          <Link to="/events" className="btn">
            All events
          </Link>
          <Link to="/events/new" className="btn btn-primary">
            + New event
          </Link>
          <Link to="/upload" className="btn">
            Upload records
          </Link>
        </div>
      </div>

      {!empty && !loading && (
        <div className={styles.inboxHero}>
          <div>
            <div className={styles.inboxLabel}>Work inbox</div>
            <div className={styles.inboxLine}>
              <strong>{inboxNeed}</strong> items need attention
              <span className={styles.inboxMuted}>
                {' '}
                · {stats?.awaiting_analysis ?? 0} analyse · {stats?.awaiting_review ?? 0} review ·{' '}
                {stats?.consistency_issues ?? 0} consistency · {stats?.high_severity_findings ?? 0}{' '}
                high severity
              </span>
            </div>
            {recentLocal.length > 0 && (
              <div className={styles.recentRow}>
                Recent:{' '}
                {recentLocal.map((r) => (
                  <Link key={r.id} to={`/events/${r.id}/summary`} className="mono">
                    {r.event_id}
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
            >
              Review queue
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => openQueue('consistency_issues')}
            >
              Consistency
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={() => openQueue('awaiting_analysis')}
            >
              Analyse
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
              <li>Create Event</li>
              <li>Upload Records</li>
              <li>Validate COMTRADE</li>
              <li>Run Analysis</li>
              <li>Review Consistency</li>
              <li>Review RCA</li>
              <li>Generate Report</li>
            </ol>
          </div>
          <div className={styles.emptyActions}>
            <Link to="/events/new" className="btn btn-primary">
              + New event
            </Link>
            <Link to="/upload" className="btn">
              Upload records
            </Link>
          </div>
        </div>
      )}

      <div className="grid-kpis">
        {kpis.map((k) => (
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
        ))}
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
          <div className="panel-body">
            {trend.length === 0 ||
            trend.every((p) => p.analysed + p.review + p.issues === 0) ? (
              <div className={styles.chartEmpty}>No events in the selected window</div>
            ) : (
              <TrendChart points={trend} />
            )}
          </div>
        </section>

        <section className={`panel ${styles.dqPanel}`}>
          <div className="panel-header">
            <span>Data quality overview</span>
          </div>
          <div className="panel-body">
            <DqDonut dq={dq} />
          </div>
        </section>

        <section className={`panel ${styles.attentionPanel}`}>
          <div className="panel-header">
            <span>Attention required</span>
            <span className={styles.badgeCount}>{attention.length}</span>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            {attention.length === 0 ? (
              <div className={styles.chartEmpty}>Nothing urgent — queue is clear</div>
            ) : (
              <ul className={styles.attentionList}>
                {attention.map((a, idx) => (
                  <li key={`${a.id}-${idx}`}>
                    <Link to={`/events/${a.id}/overview`} className="mono">
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
      </div>

      <section className="panel">
        <div className="panel-header">
          <span>Recent events</span>
          <Link to="/events">View all</Link>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <div className={styles.tableScroll}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Event ID</th>
                  <th>Date/Time</th>
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
                    <td colSpan={11} className={styles.chartEmpty}>
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
                    <td className="num">
                      {ev.event_datetime
                        ? format(parseISO(ev.event_datetime), 'yyyy-MM-dd HH:mm')
                        : '—'}
                    </td>
                    <td>{ev.location}</td>
                    <td className="mono">{ev.relay}</td>
                    <td className="mono">{ev.fault_type ?? '—'}</td>
                    <td className="mono">{ev.protection_summary}</td>
                    <td>
                      <span
                        className={
                          ev.consistency_summary.includes('findings') &&
                          !ev.consistency_summary.startsWith('0')
                            ? styles.consBad
                            : styles.consOk
                        }
                      >
                        {ev.consistency_summary}
                      </span>
                    </td>
                    <td>
                      <StatusBadge status={ev.rca_status} />
                    </td>
                    <td>
                      <StatusBadge status={ev.status} />
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
              <Link to="/events/new" className="btn btn-primary">
                + New event
              </Link>
              <Link to="/upload" className="btn">
                Upload records
              </Link>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
