import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { api } from '@/services/api';
import type { FaultClassification, Measurement, ProtectionOperation } from '@/types';
import { formatNumber, unitLabel } from '@/utils/formatElectrical';
import { DataQualityBadge } from '@/components/DataQualityBadge';
import { EmptyState } from '@/components/EmptyState';
import { PhasorDiagram, type PhasorVector } from '@/components/PhasorDiagram';
import { RXPlot } from '@/components/RXPlot';
import { HarmonicsBars } from '@/components/HarmonicsBars';
import { HarmonicsHeatmap } from '@/components/HarmonicsHeatmap';
import { QuantitySideToggle } from '@/components/QuantitySideToggle';
import { useEventOrWorkspace } from '@/context/EventWorkspaceContext';
import { useQuantitySide } from '@/hooks/useQuantitySide';
import {
  classifyChannelSide,
  detectAvailableSides,
  filterMeasurementsBySide,
  sideLabel,
} from '@/utils/quantitySide';
import { loadEventDistanceZones } from '@/utils/distanceZones';
import {
  filterImpedanceRowsForFault,
  filterRxPointsForFault,
  isRxLocusApplicable,
  rxLocusEmptyHint,
} from '@/utils/rxLocus';
import { resolveDistanceApplicable, resolveFaultType } from '@/utils/schemeContext';

/** One distinct colour per phasor — do not reuse phase colour for M1/M2/Diff/Rest. */
const PHASOR_PALETTE = [
  '#e07020',
  '#2aaa55',
  '#2a8fd4',
  '#c47a00',
  '#8b5cf6',
  '#db2777',
  '#0d9488',
  '#dc2626',
  '#2563eb',
  '#ca8a04',
  '#059669',
  '#7c3aed',
  '#ea580c',
  '#4f46e5',
  '#be185d',
  '#0891b2',
];

function colorFor(_label: string, idx: number): string {
  return PHASOR_PALETTE[idx % PHASOR_PALETTE.length];
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
  // Prefer short engineering tags on diagrams (IA / VA) — full quantity stays in tables
  const q = String(m.quantity || '')
    .replace(/_(rms|phasor|peak|pri|sec)$/gi, '')
    .replace(/_+/g, ' ')
    .trim();
  const label =
    m.phase && !q.toLowerCase().includes(String(m.phase).toLowerCase())
      ? `${q} (${m.phase})`
      : q || String(m.quantity);
  return {
    id: m.id,
    label,
    mag,
    angleDeg: Number(angle),
    unit: unitLabel(m.unit, m.quantity) !== '—' ? unitLabel(m.unit, m.quantity) : undefined,
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
                <td className="num mono">{formatNumber(m.value)}</td>
                <td className="num">
                  {m.vector?.angle_deg != null ? `${Number(m.vector.angle_deg).toFixed(1)}°` : '—'}
                </td>
                <td className="mono">{unitLabel(m.unit, m.quantity)}</td>
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
  const { analysisRevision, event } = useEventOrWorkspace(id);
  const { mode: quantitySide, setMode: setQuantitySide } = useQuantitySide(id);
  const [meas, setMeas] = useState<Measurement[]>([]);
  const [fault, setFault] = useState<FaultClassification | null>(null);
  const [protection, setProtection] = useState<ProtectionOperation[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    void Promise.all([
      api.getMeasurements(id).catch(() => [] as Measurement[]),
      api
        .getFaultClassification(id)
        .then((f) => (Array.isArray(f) ? f[0] ?? null : f))
        .catch(() => null),
      api.getProtection(id).catch(() => [] as ProtectionOperation[]),
    ])
      .then(([m, f, p]) => {
        setMeas(m);
        setFault(f);
        setProtection(Array.isArray(p) ? p : []);
      })
      .finally(() => setLoading(false));
  }, [id, analysisRevision]);

  const sides = useMemo(
    () =>
      detectAvailableSides(
        meas.map((m) => ({
          name: m.quantity.replace(/_(rms|phasor|peak)$/i, ''),
          units: m.unit,
        })),
      ),
    [meas],
  );
  const dualSide = sides.hasPrimary && sides.hasSecondary;
  const viewMode = dualSide ? quantitySide : 'both';
  const filtered = useMemo(
    () => filterMeasurementsBySide(meas, viewMode),
    [meas, viewMode],
  );

  const rms = useMemo(
    () => filtered.filter((m) => m.quantity.includes('_rms') || m.quantity === 'freq'),
    [filtered],
  );
  const phasors = useMemo(
    () => filtered.filter((m) => m.quantity.includes('_phasor')),
    [filtered],
  );
  const sequences = useMemo(
    () => filtered.filter((m) => ['I1', 'I2', 'I0', 'V1', 'V2', 'V0'].includes(m.quantity)),
    [filtered],
  );

  const faultType = useMemo(
    () =>
      resolveFaultType({
        fault,
        eventFaultType: event?.fault_type,
        eventExtra: (event?.extra || {}) as Record<string, unknown>,
      }),
    [fault, event],
  );

  const distanceApplicable = useMemo(
    () =>
      resolveDistanceApplicable({
        fault,
        protection,
        eventExtra: (event?.extra || {}) as Record<string, unknown>,
      }),
    [fault, protection, event],
  );

  const impedanceAll = useMemo(
    () => filtered.filter((m) => m.quantity.startsWith('Z_') || m.quantity.startsWith('R_')),
    [filtered],
  );
  const impedance = useMemo(
    () => filterImpedanceRowsForFault(impedanceAll, faultType),
    [impedanceAll, faultType],
  );
  const power = useMemo(
    () =>
      filtered.filter((m) =>
        /^(P_|Q_|S_|pf_|power)/i.test(m.quantity) ||
        ['P', 'Q', 'S', 'PF'].includes(m.quantity.toUpperCase()),
      ),
    [filtered],
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

  const rxPoints = useMemo(() => {
    const colors = ['#e07020', '#2aaa55', '#2a8fd4', '#c47a00'];
    return impedance
      .map((m, idx) => {
        const r =
          typeof m.vector?.R === 'number'
            ? Number(m.vector.R)
            : m.vector?.mag != null && m.vector?.angle_deg != null
              ? Number(m.vector.mag) * Math.cos((Number(m.vector.angle_deg) * Math.PI) / 180)
              : null;
        const x =
          typeof m.vector?.X === 'number'
            ? Number(m.vector.X)
            : m.vector?.mag != null && m.vector?.angle_deg != null
              ? Number(m.vector.mag) * Math.sin((Number(m.vector.angle_deg) * Math.PI) / 180)
              : null;
        if (r == null || x == null || Number.isNaN(r) || Number.isNaN(x)) return null;
        const label = String(m.phase || m.quantity || '')
          .replace(/^Z_/i, 'Z')
          .replace(/^phase_/i, 'Z');
        return {
          id: String(m.quantity || m.id),
          label: label.startsWith('Z') ? label : `Z${label}`,
          r,
          x,
          color: colors[idx % colors.length],
        };
      })
      .filter((p): p is NonNullable<typeof p> => !!p);
  }, [impedance]);

  const rxLocusOk = isRxLocusApplicable(distanceApplicable, faultType);
  const rxLocusPoints = useMemo(
    () => (rxLocusOk ? filterRxPointsForFault(rxPoints, faultType) : []),
    [rxLocusOk, rxPoints, faultType],
  );

  const zones = useMemo(() => {
    if (!rxLocusOk) return [];
    return loadEventDistanceZones((event?.extra || {}) as Record<string, unknown>);
  }, [rxLocusOk, event]);

  const harmonicSeries = useMemo(() => {
    const extra = (event?.extra || {}) as Record<string, unknown>;
    const ra = (extra.report_analysis || {}) as Record<string, unknown>;
    const ea = (ra.electrical_analysis || {}) as Record<string, unknown>;
    const harms = (ea.harmonics || {}) as Record<
      string,
      {
        value?: { harmonics_rms?: Record<string, number>; thd_percent?: number };
        status?: string;
        unit?: string;
      }
    >;
    const colors = ['#e07020', '#2aaa55', '#2a8fd4', '#c47a00'];
    return Object.entries(harms)
      .filter(([, v]) => v && v.status === 'OK' && v.value?.harmonics_rms)
      .filter(([ch, v]) => {
        if (viewMode === 'both') return true;
        const side = classifyChannelSide(ch, v.unit);
        if (side === 'unknown') return viewMode === 'secondary';
        return side === viewMode;
      })
      .slice(0, 4)
      .map(([ch, v], i) => ({
        channel: ch,
        harmonics: v.value!.harmonics_rms!,
        thdPercent: v.value?.thd_percent ?? null,
        color: colors[i % colors.length],
        unit: unitLabel(v.unit, ch) !== '—' ? unitLabel(v.unit, ch) : undefined,
      }));
  }, [event, viewMode]);

  const harmonicHeatmap = useMemo(() => {
    const extra = (event?.extra || {}) as Record<string, unknown>;
    const ra = (extra.report_analysis || {}) as Record<string, unknown>;
    const ea = (ra.electrical_analysis || {}) as Record<string, unknown>;
    const hm = (ea.harmonics_heatmap || {}) as Record<
      string,
      {
        status?: string;
        times_s?: number[];
        harmonics_rms?: Record<string, number[]>;
        unit?: string;
      }
    >;
    return Object.entries(hm)
      .filter(([, v]) => v?.status === 'OK' && (v.times_s?.length || 0) > 0)
      .filter(([ch, v]) => {
        if (viewMode === 'both') return true;
        const side = classifyChannelSide(ch, v.unit);
        if (side === 'unknown') return viewMode === 'secondary';
        return side === viewMode;
      })
      .slice(0, 3)
      .map(([ch, v]) => ({
        channel: ch,
        times_s: v.times_s || [],
        harmonics_rms: v.harmonics_rms || {},
        unit: unitLabel(v.unit, ch) !== '—' ? unitLabel(v.unit, ch) : undefined,
      }));
  }, [event, viewMode]);

  if (loading) return <div className="empty-state">Loading electrical quantities…</div>;

  if (!meas.length) {
    return (
      <EmptyState
        title="No electrical quantities yet"
        description="RMS, phasors, and sequence components from COMTRADE analogs. Impedance is shown when calculated — it is optional context, not required for every scheme."
        tips={[
          'Confirm current/voltage channels on Channel map / Waveforms',
          'Run analysis after a successful parse',
        ]}
        actions={[
          { label: 'Open Channel map', to: id ? `/events/${id}/channel-map` : '/events' },
          { label: 'Open Waveforms', to: id ? `/events/${id}/waveforms` : '/events' },
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
            Phasors · R–X · harmonics · RMS · sequence · {filtered.length} measurements
            {dualSide ? ` · ${sideLabel(quantitySide)}` : ''}
          </p>
        </div>
        <QuantitySideToggle
          mode={quantitySide}
          onChange={setQuantitySide}
          show={dualSide}
        />
      </div>

      {dualSide && quantitySide === 'primary' && (
        <div className="alert alert-info">
          Primary channel measurements (kA/kV / `*_PRI`). Sequence and Z from analysis stay on the
          Secondary view — switch there for I0/I2 and impedance.
        </div>
      )}

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

      {(sequencePhasors.length > 0 || impedancePhasors.length > 0 || rxLocusOk) && (
        <div className="two-col">
          <PhasorDiagram
            title="Sequence components"
            vectors={sequencePhasors}
            emptyHint="Sequence values present without angles — see table below."
          />
          <RXPlot
            title={
              rxLocusOk
                ? `R–X locus (${faultType || 'faulted loop'})`
                : 'R–X locus'
            }
            points={rxLocusPoints}
            zones={zones}
            emptyHint={rxLocusEmptyHint(distanceApplicable, faultType)}
          />
        </div>
      )}

      <HarmonicsBars title="Harmonic bars (fault window)" series={harmonicSeries} />
      <HarmonicsHeatmap channels={harmonicHeatmap} />

      {!hasDiagram && (
        <div className="alert alert-info">
          Phasor diagrams need magnitude and angle. Tables below show available quantities; angles
          appear when the analysis stores vector data.
        </div>
      )}

      <MeasTable rows={rms} title="RMS / frequency" />
      <MeasTable rows={phasors} title="Phasors" />
      <MeasTable rows={sequences} title="Sequence components" />
      <MeasTable rows={power} title="Power (P / Q / S)" />
      <MeasTable
        rows={impedance}
        title={
          faultType
            ? `Impedance / fault resistance (${faultType} loop)`
            : 'Impedance / fault resistance'
        }
      />
    </div>
  );
}
