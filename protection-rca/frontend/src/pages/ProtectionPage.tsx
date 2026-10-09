import { Fragment, useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { ProtectionOperation } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState } from '@/components/EmptyState';
import { DiffIrPlot, type DiffIrPoint } from '@/components/DiffIrPlot';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import { CombinedPageHeader } from '@/components/CombinedPageHeader';
import { ansiTechnicalName, formatAnsi, formatAnsiCompact } from '@/utils/ansiDeviceNames';

function detailsMeta(o: ProtectionOperation): Record<string, unknown> {
  const details = (o.details || {}) as Record<string, unknown>;
  const meta = (details.metadata || details) as Record<string, unknown>;
  return meta && typeof meta === 'object' ? meta : {};
}

function diffFromOp(o: ProtectionOperation): DiffIrPoint | null {
  const meta = detailsMeta(o);
  const diff = (meta.differential || (o.details as Record<string, unknown> | null)?.differential) as
    | {
        operate_a?: number | null;
        restraint_a?: number | null;
        operate_expected?: boolean | null;
        slope?: number;
        pickup_a?: number;
        status?: string;
      }
    | undefined;
  if (!diff || diff.status === 'NOT_CALCULABLE') return null;
  if (diff.operate_a == null || diff.restraint_a == null) return null;
  return {
    id: o.id,
    label: o.element,
    operate: Number(diff.operate_a),
    restraint: Number(diff.restraint_a),
    operated: diff.operate_expected ?? o.asserted,
    color: o.asserted ? '#e07020' : '#2aaa55',
  };
}

function physicsSummary(o: ProtectionOperation): string {
  const meta = detailsMeta(o);
  const phys = (meta.physics || {}) as Record<string, unknown>;
  const timing = ((o.details as Record<string, unknown> | null)?.timing ||
    meta.timing ||
    {}) as Record<string, unknown>;
  const el = (o.element || '').toUpperCase();
  const parts: string[] = [];

  if (el.startsWith('21')) {
    const mz = (timing.multi_zone || phys.multi_zone) as
      | Record<string, { in_zone?: boolean | null; status?: string }>
      | undefined;
    const ze = (phys.zone_entry || timing.zone_physics) as
      | { in_zone?: boolean | null; status?: string }
      | undefined;
    if (mz && typeof mz === 'object' && Object.keys(mz).length) {
      const hits = Object.entries(mz)
        .filter(([, z]) => z && z.in_zone === true)
        .map(([k]) => k);
      const anyCalculated = Object.values(mz).some(
        (z) => z && (z.status === 'CALCULATED' || z.status === 'OK' || z.in_zone != null),
      );
      const configured = Object.keys(mz).sort();
      if (hits.length) parts.push(`In ${hits.join(', ')}`);
      else if (anyCalculated) {
        parts.push(
          configured.length
            ? `Outside ${configured.join('/')}`
            : 'Outside Z1–Z5',
        );
      } else parts.push('Zone not calculable');
    } else if (ze?.status === 'NOT_CALCULABLE') {
      parts.push('Zone not calculable');
    } else if (ze?.in_zone === true) {
      parts.push('In zone');
    } else if (ze?.in_zone === false) {
      parts.push('Outside zone');
    }
    const pilot = (timing.pilot || phys.pilot) as { status?: string; pilot_consistent?: boolean } | undefined;
    if (pilot?.status === 'OK') {
      parts.push(pilot.pilot_consistent ? 'Pilot timing OK' : 'Pilot timing check');
    }
  }

  if (el === '50' || el === '50P' || el === '50N' || el === '46') {
    if (phys.status === 'OK') {
      const i = phys.current_a ?? phys.measured;
      const pu = phys.pickup_a ?? phys.pickup;
      if (i != null && pu != null) parts.push(`I=${Number(i).toFixed(1)} / Ip=${Number(pu).toFixed(1)}`);
    }
  }

  if (el === '27' || el === '59' || el.startsWith('81')) {
    if (phys.status === 'OK' && phys.measured != null && phys.pickup != null) {
      parts.push(
        `${Number(phys.measured).toFixed(3)} vs ${Number(phys.pickup).toFixed(3)} ${phys.unit || ''}`,
      );
    }
  }

  if (el === '49') {
    const mult = phys.multiple as number | undefined;
    const state = phys.thermal_state as number | undefined;
    if (mult != null) parts.push(`I/Iflc=${Number(mult).toFixed(2)}`);
    if (state != null) parts.push(`thermal=${(Number(state) * 100).toFixed(0)}%`);
  }

  if (el === '25') {
    const sync = (timing.sync || phys) as {
      permit_close?: boolean;
      dv_pu?: number;
      df_hz?: number | null;
      dphi_deg?: number;
      status?: string;
    };
    if (sync.status === 'OK' || sync.permit_close != null) {
      parts.push(sync.permit_close ? 'Permit close' : 'Block close');
      if (sync.dv_pu != null) parts.push(`ΔV=${(Number(sync.dv_pu) * 100).toFixed(1)}%`);
      if (sync.dphi_deg != null) parts.push(`Δφ=${Number(sync.dphi_deg).toFixed(1)}°`);
      if (sync.df_hz != null) parts.push(`Δf=${Number(sync.df_hz).toFixed(3)} Hz`);
    } else if (phys.status === 'NOT_CALCULABLE') {
      parts.push('Need bus & line phasors');
    }
  }

  if (el === '79') {
    const rc = (phys.reclose || timing) as {
      shots?: number;
      successful?: boolean | null;
      unsuccessful?: boolean | null;
      lockout?: boolean | null;
      reclaim_ok?: boolean | null;
    };
    const shots = rc.shots ?? timing.reclose_shots;
    if (shots != null) parts.push(`${shots} shot(s)`);
    if (rc.lockout || timing.reclose_lockout) parts.push('lockout');
    else if (rc.successful || timing.reclose_successful) parts.push('reclaim OK');
    else if (rc.unsuccessful || timing.reclose_unsuccessful) parts.push('unsuccessful');
  }

  if (el === '50BF') {
    const bf = (meta.bf_timing || timing.bf_timing || phys) as {
      bf_expected?: boolean | null;
      clearing_time_s?: number | null;
      notes?: string;
    };
    if (bf.bf_expected === true) parts.push('BF expected (current persist)');
    if (bf.bf_expected === false) parts.push('Cleared within BF timer');
    if (bf.clearing_time_s != null) parts.push(`clear ${(Number(bf.clearing_time_s) * 1000).toFixed(0)} ms`);
  }

  const diff = meta.differential as { status?: string; operate_expected?: boolean } | undefined;
  if (diff && diff.status === 'OK') {
    parts.push(diff.operate_expected ? 'Id > restrain' : 'restrained');
  }

  return parts.join(' · ') || '—';
}

export function ProtectionPage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision } = useEventOrWorkspace(id);
  const [ops, setOps] = useState<ProtectionOperation[]>([]);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    void api
      .getProtection(id)
      .then(setOps)
      .catch(() => setOps([]))
      .finally(() => setLoading(false));
  }, [id, analysisRevision]);

  const diffPoints = useMemo(
    () => ops.map(diffFromOp).filter((p): p is DiffIrPoint => !!p),
    [ops],
  );

  const diffParams = useMemo(() => {
    for (const o of ops) {
      const meta = detailsMeta(o);
      const diff = meta.differential as { slope?: number; pickup_a?: number } | undefined;
      if (diff && (diff.slope != null || diff.pickup_a != null)) {
        return {
          slope: typeof diff.slope === 'number' ? diff.slope : 0.3,
          pickup: typeof diff.pickup_a === 'number' ? diff.pickup_a : 0.2,
        };
      }
    }
    return { slope: 0.3, pickup: 0.2 };
  }, [ops]);

  if (loading) return <div className="empty-state">Loading protection assessment…</div>;

  if (!ops.length) {
    return (
      <EmptyState
        title="No protection operations yet"
        description="Pickup / trip assessments come from mapped digital channels and analysis. Without digitals or after a failed parse, this table stays empty."
        tips={[
          'Check Waveforms → Digital channels for trip / pickup bits',
          'Compare later with Consistency (needs verified settings)',
        ]}
        actions={[
          { label: 'Open Timeline', to: id ? `/events/${id}/timeline` : '/events' },
          { label: 'Open Waveforms', to: id ? `/events/${id}/waveforms` : '/events' },
        ]}
      />
    );
  }

  return (
    <div className="stack-md">
      <CombinedPageHeader
        title="Protection assessment"
        subtitle={`Observed vs expected from digitals + physics (I/V/f/Z) · ${ops.length} elements${diffPoints.length ? ' · Id/Ir characteristic (87)' : ''}`}
      />

      {diffPoints.length > 0 && (
        <div className="panel">
          <div className="panel-header">Differential characteristic (SIGRA-style Id / Ir)</div>
          <div className="panel-body" style={{ display: 'flex', justifyContent: 'center' }}>
            <DiffIrPlot
              title="Operate vs restraint"
              points={diffPoints}
              slope={diffParams.slope}
              pickup={diffParams.pickup}
            />
          </div>
        </div>
      )}

      <div className="panel">
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Element</th>
                <th>Function</th>
                <th>Operation</th>
                <th>Asserted</th>
                <th>t pickup</th>
                <th>t trip</th>
                <th>Expected</th>
                <th>Physics</th>
                <th>Conf.</th>
              </tr>
            </thead>
            <tbody>
              {ops.map((o) => {
                const summary = physicsSummary(o);
                const open = expanded === o.id;
                return (
                  <Fragment key={o.id}>
                    <tr
                      style={{ cursor: 'pointer' }}
                      onClick={() => setExpanded(open ? null : o.id)}
                    >
                      <td className="mono" title={formatAnsi(o.element)} style={{ whiteSpace: 'nowrap' }}>
                        <div>{formatAnsiCompact(o.element)}</div>
                        {ansiTechnicalName(o.element) ? (
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 400 }}>
                            {ansiTechnicalName(o.element)}
                          </div>
                        ) : null}
                      </td>
                      <td className="mono" title={formatAnsi(o.function_code)} style={{ whiteSpace: 'nowrap' }}>
                        {o.function_code ? (
                          <>
                            <div>{formatAnsiCompact(o.function_code)}</div>
                            {ansiTechnicalName(o.function_code) ? (
                              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', fontWeight: 400 }}>
                                {ansiTechnicalName(o.function_code)}
                              </div>
                            ) : null}
                          </>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>{o.operation_type}</td>
                      <td>
                        <StatusBadge
                          status={o.asserted ? 'COMPLETED' : 'CANCELLED'}
                          label={o.asserted ? 'YES' : 'NO'}
                        />
                      </td>
                      <td className="num">
                        {o.t_pickup_us != null ? `${(o.t_pickup_us / 1000).toFixed(2)} ms` : '—'}
                      </td>
                      <td className="num">
                        {o.t_trip_us != null ? `${(o.t_trip_us / 1000).toFixed(2)} ms` : '—'}
                      </td>
                      <td>{o.expected == null ? '—' : o.expected ? 'Yes' : 'No'}</td>
                      <td style={{ maxWidth: 280, fontSize: '0.78rem' }} title={summary}>
                        {summary}
                      </td>
                      <td className="num">
                        {o.confidence != null ? `${(o.confidence * 100).toFixed(0)}%` : '—'}
                      </td>
                    </tr>
                    {open && (
                      <tr>
                        <td colSpan={9} style={{ background: 'var(--bg-elevated)', fontSize: '0.78rem' }}>
                          <pre
                            style={{
                              margin: 0,
                              whiteSpace: 'pre-wrap',
                              wordBreak: 'break-word',
                              maxHeight: 220,
                              overflow: 'auto',
                            }}
                          >
                            {JSON.stringify(
                              {
                                expected_operation: (o.details as Record<string, unknown> | null)
                                  ?.expected_operation,
                                consistency: (o.details as Record<string, unknown> | null)?.consistency,
                                physics: detailsMeta(o).physics,
                                timing: (o.details as Record<string, unknown> | null)?.timing,
                                differential: detailsMeta(o).differential,
                              },
                              null,
                              2,
                            )}
                          </pre>
                        </td>
                      </tr>
                    )}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
