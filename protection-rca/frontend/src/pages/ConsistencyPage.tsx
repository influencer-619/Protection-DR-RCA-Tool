import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { ConsistencyFinding, SettingSourceInfo } from '@/types';
import { SettingSourceBanner } from '@/components/SettingSourceBanner';
import { VerifyActiveSettingsCard } from '@/components/VerifyActiveSettingsCard';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import { StatusBadge } from '@/components/StatusBadge';
import { SeverityBadge } from '@/components/SeverityBadge';
import { FindingDetail } from '@/components/FindingDetail';

type FilterKey = 'all' | 'actionable' | 'inconsistent' | 'consistent' | 'unverifiable';

function fmtCell(v: ConsistencyFinding['expected']): string {
  if (v == null) return '—';
  if (typeof v === 'string') return v;
  return Object.entries(v)
    .map(([k, val]) => `${k}=${val}`)
    .join(', ');
}

export function ConsistencyPage() {
  const { id } = useParams<{ id: string }>();
  const { event, reload: reloadEvent, analysisRevision } = useEventOrWorkspace(id);
  const [findings, setFindings] = useState<ConsistencyFinding[]>([]);
  const [source, setSource] = useState<SettingSourceInfo | null>(null);
  const [overall, setOverall] = useState('—');
  const [selected, setSelected] = useState<ConsistencyFinding | null>(null);
  const [filter, setFilter] = useState<FilterKey>('actionable');

  const load = () => {
    if (!id) return;
    void api.getConsistency(id).then((r) => {
      setFindings(r.findings);
      setSource(r.setting_source);
      setOverall(r.overall_status);
      const actionable = r.findings.filter(
        (f) =>
          f.status === 'INCONSISTENT' ||
          f.status === 'DATA_QUALITY_ISSUE' ||
          f.status === 'CONSISTENT',
      );
      if (actionable.length === 0 && r.findings.length > 0) {
        setFilter('unverifiable');
      }
    });
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, analysisRevision]);

  const counts = useMemo(() => {
    const c = {
      all: findings.length,
      consistent: 0,
      inconsistent: 0,
      unverifiable: 0,
      dq: 0,
      actionable: 0,
    };
    for (const f of findings) {
      if (f.status === 'CONSISTENT') c.consistent += 1;
      else if (f.status === 'INCONSISTENT') c.inconsistent += 1;
      else if (f.status === 'DATA_QUALITY_ISSUE') c.dq += 1;
      else c.unverifiable += 1;
    }
    c.actionable = c.consistent + c.inconsistent + c.dq;
    return c;
  }, [findings]);

  const visible = useMemo(() => {
    switch (filter) {
      case 'actionable':
        return findings.filter(
          (f) =>
            f.status === 'INCONSISTENT' ||
            f.status === 'DATA_QUALITY_ISSUE' ||
            f.status === 'CONSISTENT',
        );
      case 'inconsistent':
        return findings.filter((f) => f.status === 'INCONSISTENT');
      case 'consistent':
        return findings.filter((f) => f.status === 'CONSISTENT');
      case 'unverifiable':
        return findings.filter((f) => f.status === 'UNVERIFIABLE');
      default:
        return findings;
    }
  }, [findings, filter]);

  const settingsMissing =
    !source ||
    source.source === 'NOT AVAILABLE' ||
    source.verification_state === 'NOT VERIFIED' ||
    source.active_group_status === 'NOT VERIFIED';

  const fileNote = (
    event?.extra as { settings_file_verification_note?: string } | undefined
  )?.settings_file_verification_note;

  return (
    <div>
      <div className="page-header" style={{ padding: 0, marginBottom: 12 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Consistency checker</h1>
          <p className="subtitle">
            Setting vs observed behaviour — element-level findings (never invents a pass)
          </p>
        </div>
        <div className="badge-row">
          <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>Overall</span>
          <StatusBadge status={overall} />
        </div>
      </div>

      {source && <SettingSourceBanner source={source} />}

      {id && (
        <VerifyActiveSettingsCard
          eventId={id}
          source={source}
          settingsLoaded={Boolean(
            (event?.extra as Record<string, unknown> | undefined)?.setting_source ||
              (event?.extra as Record<string, unknown> | undefined)?.setting_param_count ||
              (event?.extra as Record<string, unknown> | undefined)?.setting_group ||
              fileNote,
          )}
          fileNote={fileNote}
          onVerified={() => {
            void reloadEvent();
            window.setTimeout(load, 2500);
          }}
        />
      )}

      {settingsMissing && (
        <div className="alert alert-warn" style={{ marginBottom: 12 }}>
          Most findings stay <strong>UNVERIFIABLE</strong> until the active setting group is{' '}
          <strong>VERIFIED</strong> and the element appears in uploaded settings or COMTRADE
          digitals. Catalog elements without file evidence are skipped. The checker will not invent
          CONSISTENT / INCONSISTENT without evidence.
        </div>
      )}

      <div className="ux-strip">
        <div className="ux-item">
          <div className="ux-label">Inconsistent</div>
          <div className="ux-value uncertain">{counts.inconsistent}</div>
        </div>
        <div className="ux-item">
          <div className="ux-label">Consistent</div>
          <div className="ux-value">{counts.consistent}</div>
        </div>
        <div className="ux-item">
          <div className="ux-label">Unverifiable</div>
          <div className="ux-value">{counts.unverifiable}</div>
        </div>
        <div className="ux-item">
          <div className="ux-label">Total checks</div>
          <div className="ux-value mono">{counts.all}</div>
        </div>
      </div>

      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
        {(
          [
            ['actionable', `Actionable (${counts.actionable})`],
            ['inconsistent', `Inconsistent (${counts.inconsistent})`],
            ['consistent', `Consistent (${counts.consistent})`],
            ['unverifiable', `Unverifiable (${counts.unverifiable})`],
            ['all', `All (${counts.all})`],
          ] as Array<[FilterKey, string]>
        ).map(([key, label]) => (
          <button
            key={key}
            type="button"
            className={`btn btn-sm ${filter === key ? 'btn-primary' : ''}`}
            onClick={() => setFilter(key)}
          >
            {label}
          </button>
        ))}
      </div>

      <div className="panel">
        <div className="panel-body" style={{ padding: 0 }}>
          {visible.length === 0 ? (
            <div className="empty-state" style={{ padding: 24 }}>
              {counts.all === 0 ? (
                <>
                  <p>No consistency findings yet — run analysis after COMTRADE upload.</p>
                  <p style={{ marginTop: 8 }}>
                    Without verified settings, many checks stay UNVERIFIABLE (intentional — not a
                    pass).
                  </p>
                </>
              ) : (
                <>
                  No findings in this filter.
                  {filter === 'actionable' && counts.unverifiable > 0 && (
                    <p style={{ marginTop: 8 }}>
                      Switch to <em>Unverifiable</em> to see checks that could not be concluded.
                    </p>
                  )}
                </>
              )}
            </div>
          ) : (
            <table className="data-table" data-testid="consistency-table">
              <thead>
                <tr>
                  <th>Element</th>
                  <th>Check</th>
                  <th>Expected</th>
                  <th>Observed</th>
                  <th>Status</th>
                  <th>Severity</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((f) => (
                  <tr
                    key={f.id}
                    style={{ cursor: 'pointer' }}
                    onClick={() => setSelected(f)}
                    data-testid={`finding-${f.finding_id}`}
                  >
                    <td className="mono">{f.element}</td>
                    <td>{f.check_type.replace(/_/g, ' ')}</td>
                    <td className="mono" style={{ fontSize: '0.75rem', maxWidth: 180 }}>
                      {fmtCell(f.expected)}
                    </td>
                    <td className="mono" style={{ fontSize: '0.75rem', maxWidth: 180 }}>
                      {fmtCell(f.observed)}
                    </td>
                    <td>
                      <StatusBadge status={f.status} />
                    </td>
                    <td>
                      <SeverityBadge severity={f.severity} />
                    </td>
                    <td className="mono" style={{ fontSize: '0.72rem' }}>
                      {f.evidence_ids?.join(', ') ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {selected && (
        <div style={{ marginTop: 16 }}>
          <FindingDetail finding={selected} onClose={() => setSelected(null)} />
        </div>
      )}
    </div>
  );
}
