import { useEffect, useMemo, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  EventWorkspaceProvider,
  useEventWorkspace,
} from '@/context/EventWorkspaceContext';
import { StatusBadge } from '@/components/StatusBadge';
import { DataQualityBadge } from '@/components/DataQualityBadge';
import { SeverityBadge } from '@/components/SeverityBadge';
import { AnalysisProgress } from '@/components/AnalysisProgress';
import { EventStatusBar, type PipelineLamp } from '@/components/EventStatusBar';
import { NextStepBanner, deriveNextStep } from '@/components/NextStepBanner';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { SharePackButton } from '@/components/SharePackButton';
import { api } from '@/services/api';
import { touchRecentEvent, removeRecentEvent } from '@/utils/recentEvents';
import { wasDrVisited } from '@/utils/drSession';
import { formatApiDateLocal, formatDrDate } from '@/utils/dateTime';
import { resolveFaultType } from '@/utils/schemeContext';
import { humanizeFaultType } from '@/utils/evidenceLabels';
import {
  effectiveEventStatus,
  isOrphanedPendingJob,
  eventHasUsableResults,
  isBlockingAnalysisFailure,
} from '@/utils/eventStatusDisplay';
import styles from './EventLayout.module.css';

type TabDef = { to: string; label: string };

const TAB_GROUPS: { id: string; label: string; tabs: TabDef[] }[] = [
  {
    id: 'setup',
    label: 'Setup',
    tabs: [
      { to: 'overview', label: 'Overview' },
      { to: 'files', label: 'Files' },
      { to: 'comtrade', label: 'COMTRADE' },
      { to: 'channel-map', label: 'Channel map' },
      { to: 'digital-map', label: 'DR targets' },
    ],
  },
  {
    id: 'analyse',
    label: 'Analyse',
    tabs: [
      { to: 'dr', label: 'DR workspace' },
      { to: 'waveforms', label: 'Waveforms' },
      { to: 'timeline', label: 'Sequence' },
      { to: 'electrical', label: 'Electrical' },
      { to: 'fault-characteristics', label: 'Fault' },
      { to: 'fault-location', label: 'Location' },
    ],
  },
  {
    id: 'protect',
    label: 'Protect',
    tabs: [
      { to: 'protection', label: 'Protection' },
      { to: 'consistency', label: 'Consistency' },
      { to: 'rca', label: 'RCA' },
      { to: 'evidence', label: 'Evidence' },
    ],
  },
  {
    id: 'conclude',
    label: 'Conclude',
    tabs: [
      { to: 'summary', label: 'Summary' },
      { to: 'report', label: 'Report' },
      { to: 'review', label: 'Review' },
    ],
  },
];

function groupForPath(pathname: string): string {
  const seg = pathname.split('/').filter(Boolean).pop() || 'overview';
  for (const g of TAB_GROUPS) {
    if (g.tabs.some((t) => t.to === seg)) return g.id;
  }
  return 'setup';
}

function lampFromBool(
  ok: boolean | null | undefined,
  warn = false,
  err = false,
): PipelineLamp['state'] {
  if (err) return 'error';
  if (warn) return 'warn';
  if (ok) return 'ok';
  if (ok === false) return 'pending';
  return 'pending';
}

function EventLayoutInner() {
  const { id } = useParams<{ id: string }>();
  const location = useLocation();
  const navigate = useNavigate();
  const {
    event,
    loading,
    reload,
    applyEvent,
    job,
    reloadJob,
    analysisRevision,
    analysisBusy: jobBusy,
  } = useEventWorkspace();
  const [consOverall, setConsOverall] = useState<string | null>(null);
  const [hasComtrade, setHasComtrade] = useState(false);
  const [hasReport, setHasReport] = useState(false);
  const [needsChannelMap, setNeedsChannelMap] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [analysing, setAnalysing] = useState(false);
  const [confirmingSettings, setConfirmingSettings] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [confirmSettings, setConfirmSettings] = useState(false);
  const [dialogError, setDialogError] = useState<string | null>(null);
  const [tabGroup, setTabGroup] = useState(() => groupForPath(location.pathname));
  const analysisBusy = analysing || confirmingSettings || jobBusy;

  useEffect(() => {
    setTabGroup(groupForPath(location.pathname));
  }, [location.pathname]);

  const onDelete = async () => {
    if (!event || !id) return;
    setDeleting(true);
    setDialogError(null);
    try {
      await api.deleteEvent(id);
      removeRecentEvent(id);
      navigate('/events', { replace: true });
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : 'Failed to delete event');
      setDeleting(false);
    }
  };

  const onAnalyse = async () => {
    if (!id) return;
    setAnalysing(true);
    setDialogError(null);
    try {
      await api.startAnalysis(id, true);
      await reloadJob();
      navigate(`/events/${id}/summary`);
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : 'Failed to start analysis');
    } finally {
      setAnalysing(false);
    }
  };

  const onConfirmSettings = async () => {
    if (!id) return;
    setConfirmSettings(false);
    setConfirmingSettings(true);
    setDialogError(null);
    try {
      await api.verifyActiveSettings(id);
      await api.startAnalysis(id, true);
      await reload();
      await reloadJob();
      void api
        .getConsistency(id)
        .then((r) => setConsOverall(r.overall_status))
        .catch(() => undefined);
      navigate(`/events/${id}/summary`);
    } catch (err) {
      setDialogError(err instanceof Error ? err.message : 'Failed to confirm active settings');
    } finally {
      setConfirmingSettings(false);
    }
  };

  useEffect(() => {
    if (!id) return;
    void api
      .getConsistency(id)
      .then((r) => setConsOverall(r.overall_status))
      .catch(() => setConsOverall(null));
    void api
      .getComtrade(id)
      .then(() => setHasComtrade(true))
      .catch(() => setHasComtrade(false));
    void api
      .getReport(id)
      .then(() => setHasReport(true))
      .catch(() => setHasReport(false));
    void api
      .getChannelMap(id)
      .then((r) => {
        const map = (r.channel_map || {}) as Record<string, string>;
        const inferred = (r.inferred_roles || {}) as Record<string, string>;
        const effective = Object.keys(map).length ? map : inferred;
        const roles = new Set(Object.values(effective).map((v) => String(v).toUpperCase()));
        const hasI = ['IA', 'IB', 'IC'].some((k) => roles.has(k));
        const hasV = ['VA', 'VB', 'VC'].some((k) => roles.has(k));
        setNeedsChannelMap(!(hasI && hasV));
      })
      .catch(() => setNeedsChannelMap(false));
  }, [id, job?.status, analysisRevision]);

  useEffect(() => {
    if (!event?.id || !event.event_id) return;
    touchRecentEvent({
      id: event.id,
      event_id: event.event_id,
      feeder: event.feeder,
      status: event.status,
    });
  }, [event?.id, event?.event_id, event?.feeder, event?.status]);

  const plant = (event?.extra as Record<string, unknown> | undefined) ?? {};

  const lamps: PipelineLamp[] = useMemo(() => {
    const dq = (event?.data_quality || '').toUpperCase();
    const decision = (event?.decision_state || '').toUpperCase();
    const cons = (consOverall || '').toUpperCase();
    const hasSettings = Boolean(
      plant.setting_source || plant.setting_param_count || plant.setting_group,
    );
    const approvalOk = String(plant.setting_approval || '').toUpperCase() === 'APPROVED';
    const groupOk = String(plant.active_group_status || 'NOT VERIFIED') === 'VERIFIED';
    const settingsWarn = hasSettings && (!approvalOk || !groupOk);
    return [
      {
        key: 'comtrade',
        label: 'COMTRADE',
        to: 'comtrade',
        state: lampFromBool(hasComtrade, false, dq === 'INVALID'),
      },
      {
        key: 'data',
        label: 'DATA',
        to: 'comtrade',
        // Green for GOOD / ACCEPTABLE / WARNING; red only for POOR / INVALID
        state: !dq
          ? 'pending'
          : ['POOR', 'INVALID'].includes(dq)
            ? 'error'
            : 'ok',
        title: !dq
          ? 'Data quality not validated yet'
          : ['POOR', 'INVALID'].includes(dq)
            ? `Data quality ${dq} — review COMTRADE before relying on results`
            : ['ACCEPTABLE', 'WARNING'].includes(dq)
              ? `Data quality ${dq} (usable) — open COMTRADE for any validation warnings`
              : `Data quality ${dq}`,
      },
      {
        key: 'settings',
        label: 'SETTINGS',
        to: 'consistency',
        state: !hasSettings ? 'pending' : settingsWarn ? 'warn' : 'ok',
      },
      {
        key: 'protection',
        label: 'PROTECTION',
        to: 'protection',
        state: lampFromBool(
          job?.status === 'COMPLETED' ||
            eventHasUsableResults(event) ||
            ['ANALYSED', 'REVIEW', 'CLOSED'].includes((event?.status || '').toUpperCase()),
        ),
      },
      {
        key: 'consistency',
        label: 'CONSISTENCY',
        to: 'consistency',
        state:
          cons === 'INCONSISTENT'
            ? 'error'
            : cons === 'CONSISTENT'
              ? 'ok'
              : cons === 'UNVERIFIABLE'
                ? 'warn'
                : 'pending',
      },
      {
        key: 'rca',
        label: 'RCA',
        to: 'rca',
        state:
          decision === 'INCONCLUSIVE' || decision === 'DATA_INSUFFICIENT'
            ? 'warn'
            : decision
              ? 'ok'
              : 'pending',
      },
      {
        key: 'report',
        label: 'REPORT',
        to: 'report',
        state: hasReport ? 'ok' : 'pending',
      },
    ];
  }, [event, consOverall, hasComtrade, hasReport, job?.status, plant]);

  const hasResults = eventHasUsableResults(event);
  const blockingFail = isBlockingAnalysisFailure(event, job?.status);
  const displayStatus = effectiveEventStatus(event, job?.status, job);

  const nextStep = useMemo(() => {
    if (!id || !event) return null;
    return deriveNextStep({
      eventId: id,
      lamps,
      analysisBusy,
      jobStatus: job?.status,
      onAnalyse: () => void onAnalyse(),
      onConfirmSettings: () => setConfirmSettings(true),
      needsChannelMap: hasComtrade && needsChannelMap,
      preferDr:
        (job?.status === 'COMPLETED' || (hasResults && !blockingFail)) && !wasDrVisited(id),
      hasUsableResults: hasResults,
    });
  }, [
    id,
    event,
    lamps,
    analysisBusy,
    job?.status,
    hasComtrade,
    needsChannelMap,
    hasResults,
    blockingFail,
  ]);

  const substationLabel = event?.substation_name ?? 'UNKNOWN';
  const bayLabel = event?.bay_name ?? 'NOT VERIFIED';
  const relayLabel = event?.relay_tag ?? 'NOT VERIFIED';
  const feederLabel = event?.feeder ?? null;

  const faultTypeRaw = resolveFaultType({
    eventFaultType: event?.fault_type,
    eventExtra: plant,
  });
  const _ra = (plant.report_analysis || {}) as Record<string, unknown>;
  const _fc = (_ra.fault_classification || {}) as Record<string, unknown>;
  const _evc = (_fc.event_class ||
    (_fc.evidence as { event_classification?: { event_class?: string } } | undefined)
      ?.event_classification?.event_class ||
    (_fc.features as { event_class?: string } | undefined)?.event_class) as
    | string
    | undefined;
  const faultType = humanizeFaultType(faultTypeRaw, _evc);

  const normalizedJob = useMemo(() => {
    if (!job) return null;
    if (Array.isArray(job.stages) && job.stages.length && typeof job.stages[0] === 'object') {
      return job;
    }
    const names = [
      'Upload',
      'Detection',
      'COMTRADE Validation',
      'Parsing',
      'Signal Processing',
      'Event Reconstruction',
      'Protection Analysis',
      'Consistency Checker',
      'Fault Classification',
      'RCA',
      'Evidence',
      'Report',
    ];
    const pct = job.progress ?? 0;
    const stages = names.map((label, i) => {
      const threshold = ((i + 1) / names.length) * 100;
      let status: 'pending' | 'running' | 'done' | 'failed' = 'pending';
      if (job.status === 'FAILED' && pct >= (i / names.length) * 100 && pct < threshold) {
        status = 'failed';
      } else if (pct >= threshold || job.status === 'COMPLETED') {
        status = 'done';
      } else if (pct >= (i / names.length) * 100) {
        status = 'running';
      }
      return { name: label.toLowerCase().replace(/\s+/g, '_'), label, status };
    });
    return { ...job, stages };
  }, [job]);

  const activeGroup = TAB_GROUPS.find((g) => g.id === tabGroup) || TAB_GROUPS[0];

  return (
    <div className={styles.wrap}>
      <div className={styles.headBand}>
        <div className={styles.header}>
          <div className={styles.headMain}>
            <div className={styles.headIcon} aria-hidden>
              <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <path d="M3 12h4l3-8 4 16 3-8h4" />
              </svg>
            </div>
            <div className={styles.headText}>
              <div className={styles.crumbs}>
                <span>{substationLabel}</span>
                <span className={styles.sep}>›</span>
                <span>{bayLabel}</span>
                <span className={styles.sep}>›</span>
                <span className="mono">{relayLabel}</span>
              </div>
              <h1 className={styles.title}>
                <span className="mono">{event?.event_id ?? id}</span>
                {feederLabel && <span className={styles.feeder}>{feederLabel}</span>}
              </h1>
              <div className={styles.badges}>
                {loading && <span className={styles.loading}>Loading…</span>}
                <span
                  className={`mono ${styles.when}`}
                  title="Relay disturbance time from COMTRADE (wall clock as on the DR file)"
                >
                  DR {formatDrDate(event?.event_datetime)}
                </span>
                {event?.created_at && (
                  <span
                    className={`mono ${styles.when}`}
                    title="Created in this application — shown in your local timezone"
                    style={{ opacity: 0.85 }}
                  >
                    Created {formatApiDateLocal(event.created_at)}
                  </span>
                )}
                {event?.status && (
                  <StatusBadge
                    status={displayStatus}
                    title={
                      (String(event.status).toUpperCase() === 'FAILED' ||
                        isOrphanedPendingJob(job)) &&
                      hasResults
                        ? [
                            'Prior analysis results are shown (latest run did not finish).',
                            job?.error_message || 'Use Re-run analysis to refresh results.',
                          ].join('\n')
                        : event.status === 'FAILED' && job?.error_message
                          ? job.error_message
                          : undefined
                    }
                  />
                )}
                {event?.decision_state && <StatusBadge status={event.decision_state} />}
                {event?.data_quality && <DataQualityBadge quality={event.data_quality} />}
                {faultType && <span className={`mono ${styles.fault}`}>{faultType}</span>}
                {event?.severity_summary && <SeverityBadge severity={event.severity_summary} />}
              </div>
            </div>
          </div>
          {event && (
            <div className={styles.actions}>
              {id && <SharePackButton eventId={id} eventCode={event.event_id} />}
              <button
                type="button"
                className="btn btn-sm btn-primary"
                disabled={analysisBusy || deleting}
                onClick={() => void onAnalyse()}
              >
                {analysisBusy
                  ? 'Analysing…'
                  : job?.status === 'COMPLETED'
                    ? 'Re-run analysis'
                    : 'Start analysis'}
              </button>
              <button
                type="button"
                className={`btn btn-sm ${styles.deleteBtn}`}
                disabled={deleting || analysisBusy}
                onClick={() => setConfirmDelete(true)}
                title="Delete event"
                aria-label="Delete event"
              >
                <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                  <path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" />
                </svg>
                {deleting && <span>Deleting…</span>}
              </button>
            </div>
          )}
        </div>

        <EventStatusBar lamps={lamps} eventBase={id ? `/events/${id}` : undefined} />
      </div>

      {dialogError && (
        <div className="alert alert-danger" style={{ margin: '12px var(--content-pad-x) 0' }}>
          {dialogError}
        </div>
      )}

      {(nextStep ||
        (normalizedJob &&
          normalizedJob.status !== 'COMPLETED' &&
          (blockingFail ||
            normalizedJob.status === 'RUNNING' ||
            normalizedJob.status === 'PENDING'))) && (
        <div className={styles.guide}>
          {nextStep && <NextStepBanner step={nextStep} />}
          {normalizedJob &&
            (normalizedJob.status === 'RUNNING' ||
              normalizedJob.status === 'PENDING' ||
              blockingFail) && (
              <AnalysisProgress job={normalizedJob as never} compact />
            )}
        </div>
      )}

      <nav className={styles.nav} aria-label="Event sections">
        <div className={styles.groups} role="tablist">
          {TAB_GROUPS.map((g) => (
            <button
              key={g.id}
              type="button"
              role="tab"
              aria-selected={tabGroup === g.id}
              className={`${styles.groupBtn} ${tabGroup === g.id ? styles.groupActive : ''}`}
              onClick={() => {
                setTabGroup(g.id);
                const first = g.tabs[0];
                if (first && id) navigate(`/events/${id}/${first.to}`);
              }}
            >
              {g.label}
            </button>
          ))}
        </div>
        <div className={styles.tabs}>
          {activeGroup.tabs.map((t) => (
            <NavLink
              key={t.to}
              to={`/events/${id}/${t.to}`}
              className={({ isActive }) => `${styles.tab} ${isActive ? styles.active : ''}`}
            >
              {t.label}
            </NavLink>
          ))}
        </div>
      </nav>

      <div className={styles.body}>
        <Outlet
          key={`${location.pathname}::${analysisRevision}`}
          context={{ applyEvent, analysisRevision, reload }}
        />
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete event?"
        message={`Delete event ${event?.event_id}?\n\nThis removes the event and analysis results from the database. The action is audited.`}
        confirmLabel="Delete"
        danger
        busy={deleting}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => void onDelete()}
      />
      <ConfirmDialog
        open={confirmSettings}
        title="Confirm active settings?"
        message="Confirm that the uploaded setting group was the ACTIVE group on the relay at the time of this disturbance?\n\nThis re-runs analysis so Consistency uses VERIFIED."
        confirmLabel="Confirm & re-run"
        busy={confirmingSettings}
        onCancel={() => setConfirmSettings(false)}
        onConfirm={() => void onConfirmSettings()}
      />
    </div>
  );
}

export function EventLayout() {
  const { id } = useParams<{ id: string }>();
  return (
    <EventWorkspaceProvider eventId={id}>
      <EventLayoutInner />
    </EventWorkspaceProvider>
  );
}
