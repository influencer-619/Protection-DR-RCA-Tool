import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { FaultCharacteristics } from '@/types';
import { StatusBadge } from '@/components/StatusBadge';
import { EmptyState } from '@/components/EmptyState';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';

function fmtMs(t_us: number | null | undefined): string {
  if (t_us == null) return '—';
  return `${(t_us / 1000).toFixed(2)} ms`;
}

function fmtNum(v: unknown, digits = 2): string {
  if (v == null || v === '') return '—';
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  return n.toFixed(digits);
}

export function FaultCharacteristicsPage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision } = useEventOrWorkspace(id);
  const [data, setData] = useState<FaultCharacteristics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    void api
      .getFaultCharacteristics(id)
      .then(setData)
      .catch((e: unknown) => {
        setData(null);
        setError(e instanceof Error ? e.message : 'Not available');
      })
      .finally(() => setLoading(false));
  }, [id, analysisRevision]);

  if (loading) return <div className="empty-state">Loading fault characteristics…</div>;

  if (error || !data) {
    return (
      <EmptyState
        title="Fault characteristics not available"
        description="Run analysis after uploading COMTRADE. Add settings when you need consistency checks or optional location estimates."
        actions={[
          { label: 'Go to Files', to: id ? `/events/${id}/files` : '/events', primary: true },
          { label: 'Open Overview', to: id ? `/events/${id}/overview` : '/events' },
        ]}
      />
    );
  }

  const c = data.currents || {};
  const distApplicable =
    (data as { distance_applicable?: boolean }).distance_applicable === true ||
    data.distance_km != null;
  const hasLocation =
    distApplicable &&
    (data.distance_km != null ||
      (data.location_algorithms && data.location_algorithms.length > 0) ||
      !!data.location_method);
  const limitations = (data.limitations || []).filter(
    (l) =>
      distApplicable ||
      (!/FAULT\s*DISTANCE/i.test(l) && !/Z1\s*\/\s*km/i.test(l) && !/line Z1/i.test(l)),
  );

  return (
    <div className="stack-md">
      <div className="page-header" style={{ padding: 0, marginBottom: 0 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Fault characteristics</h1>
          <p className="subtitle">
            Scheme-agnostic summary — type, timing, magnitudes, sequences (no invented values)
          </p>
        </div>
        <Link className="btn btn-sm" to={`/events/${id}/fault-location`}>
          Location (optional)
        </Link>
      </div>

      <div className="grid-kpis">
        <div className="kpi-card info">
          <div className="kpi-label">Fault type</div>
          <div className="kpi-value mono">{data.fault_type}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Status</div>
          <div className="kpi-value">
            <StatusBadge status={data.status} />
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Confidence</div>
          <div className="kpi-value mono">{data.confidence_level ?? '—'}</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">Location</div>
          <div className="kpi-value mono" style={{ fontSize: hasLocation || !distApplicable ? '0.85rem' : undefined }}>
            {data.distance_km != null
              ? `${fmtNum(data.distance_km)} km`
              : distApplicable
                ? hasLocation
                  ? 'See Location tab'
                  : 'NOT CALCULABLE'
                : 'Not applicable'}
          </div>
        </div>
      </div>

      <div className="two-col">
        <div className="panel">
          <div className="panel-header">Timing</div>
          <div className="panel-body">
            <table className="data-table">
              <tbody>
                <tr>
                  <td>Inception</td>
                  <td className="mono">{fmtMs(data.inception_t_us)}</td>
                </tr>
                <tr>
                  <td>Pickup</td>
                  <td className="mono">{fmtMs(data.pickup_t_us)}</td>
                </tr>
                <tr>
                  <td>Trip</td>
                  <td className="mono">{fmtMs(data.trip_t_us)}</td>
                </tr>
                <tr>
                  <td>Clearing / 52A</td>
                  <td className="mono">{fmtMs(data.clearing_t_us)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div className="panel">
          <div className="panel-header">Phases & ground</div>
          <div className="panel-body">
            <p>
              Involved: <span className="mono">{(data.involved_phases || []).join(', ') || '—'}</span>
            </p>
            <p>
              Ground involved:{' '}
              <span className="mono">
                {data.ground_involved == null ? '—' : data.ground_involved ? 'YES' : 'NO'}
              </span>
            </p>
            <p>
              Location method:{' '}
              <span className="mono">{data.location_method ?? 'N/A (optional)'}</span>
            </p>
          </div>
        </div>
      </div>

      <div className="panel">
        <div className="panel-header">Fault-window currents (RMS / sequence)</div>
        <div className="panel-body" style={{ padding: 0 }}>
          <table className="data-table">
            <thead>
              <tr>
                <th>Quantity</th>
                <th>Value</th>
                <th>Elevated</th>
              </tr>
            </thead>
            <tbody>
              {(['Ia', 'Ib', 'Ic'] as const).map((k) => (
                <tr key={k}>
                  <td className="mono">{k}</td>
                  <td className="mono">{fmtNum(c[k])}</td>
                  <td className="mono">
                    {c[`${k}_elevated` as keyof typeof c] == null
                      ? '—'
                      : c[`${k}_elevated` as keyof typeof c]
                        ? 'YES'
                        : 'NO'}
                  </td>
                </tr>
              ))}
              <tr>
                <td className="mono">I0</td>
                <td className="mono">{fmtNum(data.sequences?.I0)}</td>
                <td>—</td>
              </tr>
              <tr>
                <td className="mono">I2</td>
                <td className="mono">{fmtNum(data.sequences?.I2)}</td>
                <td>—</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {data.line_impedance_estimate && distApplicable && (
        <div className="panel">
          <div className="panel-header">Line impedance (from settings)</div>
          <div className="panel-body">
            <p className="mono" style={{ fontSize: '0.85rem' }}>
              Status: {String(data.line_impedance_estimate.status ?? '—')} · Length:{' '}
              {fmtNum(data.line_impedance_estimate.length_km)} km
            </p>
            {Boolean(data.line_impedance_estimate.z1_ohm_per_km) && (
              <p className="mono" style={{ fontSize: '0.85rem' }}>
                Z1/km: R={fmtNum((data.line_impedance_estimate.z1_ohm_per_km as { R?: number }).R)}{' '}
                X={fmtNum((data.line_impedance_estimate.z1_ohm_per_km as { X?: number }).X)} Ω
              </p>
            )}
            {Boolean(data.line_impedance_estimate.z0_ohm_per_km) && (
              <p className="mono" style={{ fontSize: '0.85rem' }}>
                Z0/km: R={fmtNum((data.line_impedance_estimate.z0_ohm_per_km as { R?: number }).R)}{' '}
                X={fmtNum((data.line_impedance_estimate.z0_ohm_per_km as { X?: number }).X)} Ω
              </p>
            )}
          </div>
        </div>
      )}

      {limitations.length > 0 && (
        <div className="alert alert-warn">
          <strong>Limitations</strong>
          <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
            {limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
