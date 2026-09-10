import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { ProtectionOperation } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState } from '@/components/EmptyState';
import { DiffIrPlot, type DiffIrPoint } from '@/components/DiffIrPlot';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';

function diffFromOp(o: ProtectionOperation): DiffIrPoint | null {
  const details = (o.details || {}) as Record<string, unknown>;
  const meta = (details.metadata || details) as Record<string, unknown>;
  const diff = (meta.differential || details.differential) as
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

export function ProtectionPage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision } = useEventOrWorkspace(id);
  const [ops, setOps] = useState<ProtectionOperation[]>([]);
  const [loading, setLoading] = useState(true);

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
      const details = (o.details || {}) as Record<string, unknown>;
      const meta = (details.metadata || details) as Record<string, unknown>;
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
      <div className="page-header" style={{ padding: 0, marginBottom: 0 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Protection assessment</h1>
          <p className="subtitle">
            Observed element operations vs expected behaviour · {ops.length} elements
            {diffPoints.length ? ' · Id/Ir characteristic (87)' : ''}
          </p>
        </div>
      </div>

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
                <th>Breaker</th>
                <th>Conf.</th>
              </tr>
            </thead>
            <tbody>
              {ops.map((o) => (
                <tr key={o.id}>
                  <td className="mono">{o.element}</td>
                  <td className="mono">{o.function_code ?? '—'}</td>
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
                  <td className="mono">{o.breaker_assessment ?? '—'}</td>
                  <td className="num">
                    {o.confidence != null ? `${(o.confidence * 100).toFixed(0)}%` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
