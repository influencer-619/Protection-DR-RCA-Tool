import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { Measurement } from '@/types';
import { DataQualityBadge } from '@/components/DataQualityBadge';
import { EmptyState } from '@/components/EmptyState';
import { PhasorDiagram, type PhasorVector } from '@/components/PhasorDiagram';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';

const PHASE_COLORS: Record<string, string> = {
  a: '#e07020',
  b: '#2aaa55',
  c: '#2a8fd4',
  ia: '#e07020',
  ib: '#2aaa55',
  ic: '#2a8fd4',
  va: '#c45a12',
  vb: '#1f7a3a',
  vc: '#0b6e99',
  i1: '#00a0b4',
  i2: '#c47a00',
  i0: '#5c7188',
  v1: '#007a8a',
  v2: '#c45a12',
  v0: '#8fa3b8',
};

function colorFor(label: string, idx: number): string {
  const k = label.toLowerCase().replace(/[^a-z0-9]/g, '');
  for (const [key, c] of Object.entries(PHASE_COLORS)) {
    if (k.includes(key)) return c;
  }
  const fallback = ['#e07020', '#2aaa55', '#2a8fd4', '#c47a00', '#00a0b4', '#0b3a5b'];
  return fallback[idx % fallback.length];
}

function toPhasor(m: Measurement, idx: number): PhasorVector | null {
  const angle = m.vector?.angle_deg;
  if (angle == null || Number.isNaN(Number(angle))) return null;
  const mag =
    m.vector?.mag != null && !Number.isNaN(Number(m.vector.mag))
      ? Number(m.vector.mag)
      : m.value != null
        ? Number(m.value)
        : null;
  if (mag == null || Number.isNaN(mag)) return null;
  const label =
    m.phase && !m.quantity.toLowerCase().includes(String(m.phase).toLowerCase())
      ? `${m.quantity} (${m.phase})`
      : m.quantity;
  return {
    id: m.id,
    label,
    mag,
    angleDeg: Number(angle),
    unit: m.unit ?? undefined,
    color: colorFor(label, idx),
  };
}

function MeasTable({ rows, title }: { rows: Measurement[]; title: string }) {
  if (!rows.length) {
    return (
      <div className="panel">
        <div className="panel-header">{title}</div>
        <div className="panel-body" style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
          No quantities in this group (channels missing or not calculable).
        </div>
      </div>
    );
  }
  return (
    <div className="panel">
      <div className="panel-header">{title}</div>
      <div className="panel-body" style={{ padding: 0 }}>
        <table className="data-table">
          <thead>
            <tr>
              <th>Quantity</th>
              <th>Phase</th>
              <th>Value</th>
              <th>Angle</th>
              <th>Unit</th>
              <th>Algorithm</th>
              <th>DQ</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((m) => (
              <tr key={m.id}>
                <td className="mono">{m.quantity}</td>
                <td className="mono">{m.phase ?? '—'}</td>
                <td className="num">{m.value?.toFixed?.(3) ?? m.value ?? '—'}</td>
                <td className="num">
                  {m.vector?.angle_deg != null ? `${m.vector.angle_deg.toFixed(1)}°` : '—'}
                </td>
                <td>{m.unit ?? '—'}</td>
                <td className="mono">{m.algorithm ?? '—'}</td>
                <td>{m.quality ? <DataQualityBadge quality={m.quality} /> : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export function ElectricalPage() {
  const { id } = useParams<{ id: string }>();
  const { analysisRevision } = useEventOrWorkspace(id);
  const [meas, setMeas] = useState<Measurement[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    void api
      .getMeasurements(id)
      .then(setMeas)
      .catch(() => setMeas([]))
      .finally(() => setLoading(false));
  }, [id, analysisRevision]);

  const rms = useMemo(
    () => meas.filter((m) => m.quantity.includes('_rms') || m.quantity === 'freq'),
    [meas],
  );
  const phasors = useMemo(() => meas.filter((m) => m.quantity.includes('_phasor')), [meas]);
  const sequences = useMemo(
    () => meas.filter((m) => ['I1', 'I2', 'I0', 'V1', 'V2', 'V0'].includes(m.quantity)),
    [meas],
  );
  const impedance = useMemo(
    () => meas.filter((m) => m.quantity.startsWith('Z_') || m.quantity.startsWith('R_')),
    [meas],
  );

  const currentPhasors = useMemo(() => {
    const rows = phasors.filter((m) => /^i/i.test(m.quantity) || (m.phase && /i/i.test(m.phase)));
    const src = rows.length ? rows : phasors.filter((m) => /i[abc]|ia|ib|ic/i.test(m.quantity));
    return (src.length ? src : phasors.filter((m) => m.quantity.toLowerCase().includes('i')))
      .map(toPhasor)
      .filter((v): v is PhasorVector => !!v);
  }, [phasors]);

  const voltagePhasors = useMemo(() => {
    const rows = phasors.filter((m) => /^v/i.test(m.quantity) || (m.phase && /v/i.test(m.phase)));
    const src = rows.length ? rows : phasors.filter((m) => /v[abc]|va|vb|vc/i.test(m.quantity));
    return (src.length ? src : phasors.filter((m) => m.quantity.toLowerCase().includes('v')))
      .map(toPhasor)
      .filter((v): v is PhasorVector => !!v);
  }, [phasors]);

  const sequencePhasors = useMemo(
    () => sequences.map(toPhasor).filter((v): v is PhasorVector => !!v),
    [sequences],
  );

  const impedancePhasors = useMemo(
    () => impedance.map(toPhasor).filter((v): v is PhasorVector => !!v),
    [impedance],
  );

  if (loading) return <div className="empty-state">Loading electrical quantities…</div>;

  if (!meas.length) {
    return (
      <EmptyState
        title="No electrical quantities yet"
        description="RMS, phasors, and sequence components from COMTRADE analogs. Impedance is shown when calculated — it is optional context, not required for every scheme."
        tips={[
          'Confirm current/voltage channels on COMTRADE / Waveforms',
          'Run analysis after a successful parse',
        ]}
        actions={[
          { label: 'Open Waveforms', to: id ? `/events/${id}/waveforms` : '/events' },
          { label: 'Open COMTRADE', to: id ? `/events/${id}/comtrade` : '/events' },
        ]}
      />
    );
  }

  const hasDiagram =
    currentPhasors.length > 0 ||
    voltagePhasors.length > 0 ||
    sequencePhasors.length > 0 ||
    impedancePhasors.length > 0;

  return (
    <div className="stack-md">
      <div className="page-header" style={{ padding: 0, marginBottom: 0 }}>
        <div>
          <h1 style={{ fontSize: '1.1rem' }}>Electrical quantities</h1>
          <p className="subtitle">
            Phasor diagrams · RMS · sequence · impedance · {meas.length} measurements
          </p>
        </div>
      </div>

      {hasDiagram && (
        <div className="two-col">
          <PhasorDiagram
            title="Current phasors"
            vectors={currentPhasors}
            emptyHint="No current phasor angles in this event."
          />
          <PhasorDiagram
            title="Voltage phasors"
            vectors={voltagePhasors}
            emptyHint="No voltage phasor angles in this event."
          />
        </div>
      )}

      {(sequencePhasors.length > 0 || impedancePhasors.length > 0) && (
        <div className="two-col">
          <PhasorDiagram
            title="Sequence components"
            vectors={sequencePhasors}
            emptyHint="Sequence values present without angles — see table below."
          />
          <PhasorDiagram
            title="Impedance vectors"
            vectors={impedancePhasors}
            emptyHint="Impedance magnitude only (no angle) — see table."
          />
        </div>
      )}

      {!hasDiagram && (
        <div className="alert alert-info">
          Phasor diagrams need magnitude and angle. Tables below show available quantities; angles
          appear when the analysis stores vector data.
        </div>
      )}

      <MeasTable rows={rms} title="RMS / frequency" />
      <MeasTable rows={phasors} title="Phasors" />
      <MeasTable rows={sequences} title="Sequence components" />
      <MeasTable rows={impedance} title="Impedance / fault resistance" />
    </div>
  );
}
