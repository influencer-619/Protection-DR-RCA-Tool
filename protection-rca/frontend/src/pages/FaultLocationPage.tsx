import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { FaultCharacteristics, FaultLocationRow } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState } from '@/components/EmptyState';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';

function fmt(v: number | null | undefined, d = 2): string {
  if (v == null || !Number.isFinite(v)) return '—';
  return v.toFixed(d);
}

export function FaultLocationPage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision } = useEventOrWorkspace(id);
  const [rows, setRows] = useState<FaultLocationRow[]>([]);
  const [meta, setMeta] = useState<FaultCharacteristics | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    void api
      .getFaultCharacteristics(id)
      .then((r) => {
        setMeta(r);
        setRows(r.distance_applicable === true ? (r.location_algorithms ?? []) : []);
      })
      .catch(() => {
        setMeta(null);
        setRows([]);
      })
      .finally(() => setLoading(false));
  }, [id, analysisRevision]);

  if (loading) return <div className="empty-state">Loading fault location…</div>;

  if (!meta) {
    return (
      <EmptyState
        title="Location estimate not available"
        description="Optional for distance / line cases. Upload COMTRADE + line parameters (and operate distance elements) when a km estimate is needed. Overcurrent / differential / BF cases do not require this tab."
        actions={[{ label: 'Go to Files', to: id ? `/events/${id}/files` : '/events', primary: true }]}
      />
    );
  }

  const applicable = meta.distance_applicable === true;

  if (!applicable) {
    return (
      <div className="stack-md">
        <div className="page-header" style={{ padding: 0, marginBottom: 0 }}>
          <div>
            <h1 style={{ fontSize: '1.1rem' }}>Location (optional)</h1>
            <p className="subtitle">Not used for this protection scheme</p>
          </div>
          <Link className="btn btn-sm" to={`/events/${id}/fault-characteristics`}>
            Fault characteristics
          </Link>
        </div>
        <EmptyState
          title="Fault distance not applicable"
          description="This event is not a distance (21) case — e.g. differential (87), overcurrent, or earth fault. No km estimate is shown. Continue with Protection → Consistency → RCA."
          actions={[
            { label: 'Fault characteristics', to: `/events/${id}/fault-characteristics`, primary: true },
            { label: 'Protection', to: `/events/${id}/protection` },
          ]}
        />
      </div>
    );
  }

  const hasRows = rows.length > 0 || meta.distance_km != null;

  return (
    <div className="stack-md">
      <div className="page-header" style={{ padding: 0, marginBottom: 0 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Location (optional)</h1>
          <p className="subtitle">
            Single-ended estimates when line data exists — distance (21) scheme only
          </p>
        </div>
        <Link className="btn btn-sm" to={`/events/${id}/fault-characteristics`}>
          Fault characteristics
        </Link>
      </div>

      {!hasRows && (
        <div className="alert alert-info">
          Distance scheme applies but no km was calculable (need validated line Z1 / CT-VT). Continue
          with Protection → Consistency → RCA.
        </div>
      )}

      <div className="alert alert-info">
        Fault type <span className="mono">{meta.fault_type}</span>
        {meta.distance_km != null && (
          <>
            {' '}
            · Preferred:{' '}
            <span className="mono">
              {fmt(meta.distance_km)} km ({meta.location_method ?? '—'})
            </span>
          </>
        )}
      </div>

      <div className="panel">
        <div className="panel-body" style={{ padding: 0 }}>
          {rows.length === 0 ? (
            <div className="empty-state" style={{ padding: 24 }}>
              No km estimate stored — expected when line parameters are missing. Re-run analysis after
              adding line Z1 if a location estimate is required.
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Algorithm</th>
                  <th>Distance</th>
                  <th>Distance %</th>
                  <th>Unit</th>
                  <th>Status</th>
                  <th>Notes</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.algorithm}>
                    <td>{r.algorithm}</td>
                    <td className="mono">
                      {r.distance_km != null ? `${fmt(r.distance_km)} ${r.unit || 'km'}` : '—'}
                    </td>
                    <td className="mono">
                      {r.distance_pct != null ? `${fmt(r.distance_pct, 1)}%` : '—'}
                    </td>
                    <td className="mono">{r.unit}</td>
                    <td>
                      <StatusBadge status={r.status} />
                    </td>
                    <td style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{r.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {meta.line_impedance_estimate && (
        <div className="panel">
          <div className="panel-header">Line impedance estimate (settings)</div>
          <div className="panel-body mono" style={{ fontSize: '0.85rem' }}>
            {JSON.stringify(meta.line_impedance_estimate, null, 2)}
          </div>
        </div>
      )}
    </div>
  );
}
