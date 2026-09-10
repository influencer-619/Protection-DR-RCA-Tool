import type { WaveformChannelData } from '@/types';
import { rmsNear, sampleAtTime } from '@/utils/waveformCalc';
import { formatElectrical, inferUnitFromName, unitLabel } from '@/utils/formatElectrical';
import {
  classifyChannelSide,
  type QuantitySideMode,
} from '@/utils/quantitySide';
import styles from './CursorReadout.module.css';

interface Props {
  channels: WaveformChannelData[];
  cursorA: number | null;
  cursorB: number | null;
  tMin: number;
  /** Prefer primary or secondary when both IA and IA_PRI exist. */
  quantitySide?: QuantitySideMode;
}

function pick(
  channels: WaveformChannelData[],
  re: RegExp,
  mode: QuantitySideMode = 'secondary',
) {
  const hits = channels.filter((c) =>
    re.test(`${c.channel.name} ${c.channel.phase || ''}`.toUpperCase()),
  );
  if (!hits.length) return undefined;
  if (mode === 'both') {
    // Prefer secondary label for the readout when both are plotted
    return (
      hits.find(
        (c) =>
          classifyChannelSide(c.channel.name, c.channel.units, c.channel.ps) === 'secondary',
      ) || hits[0]
    );
  }
  const want = mode === 'primary' ? 'primary' : 'secondary';
  return (
    hits.find(
      (c) => classifyChannelSide(c.channel.name, c.channel.units, c.channel.ps) === want,
    ) ||
    hits.find(
      (c) => classifyChannelSide(c.channel.name, c.channel.units, c.channel.ps) === 'unknown',
    ) ||
    hits[0]
  );
}

function cell(ch: WaveformChannelData | undefined, t: number | null, rms: boolean) {
  if (!ch || t == null) return '—';
  const v = rms ? rmsNear(ch, t) : sampleAtTime(ch, t);
  const unit = inferUnitFromName(ch.channel.name, ch.channel.units);
  return formatElectrical(v, unit, { nameHint: ch.channel.name, digits: 3 });
}

export function CursorReadout({
  channels,
  cursorA,
  cursorB,
  tMin,
  quantitySide = 'secondary',
}: Props) {
  if (cursorA == null && cursorB == null) return null;
  const roles = [
    { label: 'IA', re: /\bIA\b|\bIL1\b|\bI1\b/ },
    { label: 'IB', re: /\bIB\b|\bIL2\b|\bI2\b/ },
    { label: 'IC', re: /\bIC\b|\bIL3\b|\bI3\b/ },
    { label: 'VA', re: /\bVA\b|\bUL1\b|\bV1\b/ },
    { label: 'VB', re: /\bVB\b|\bUL2\b|\bV2\b/ },
    { label: 'VC', re: /\bVC\b|\bUL3\b|\bV3\b/ },
  ];
  const dt =
    cursorA != null && cursorB != null ? Math.abs(cursorB - cursorA) / 1000 : null;

  const unitHints = roles.map((r) => {
    const ch = pick(channels, r.re, quantitySide);
    return unitLabel(ch?.channel.units, r.label);
  });

  return (
    <div className={styles.strip}>
      <div className={styles.meta}>
        {cursorA != null && (
          <span>
            A <span className="mono">{((cursorA - tMin) / 1000).toFixed(3)} ms</span>
          </span>
        )}
        {cursorB != null && (
          <span>
            B <span className="mono">{((cursorB - tMin) / 1000).toFixed(3)} ms</span>
          </span>
        )}
        {dt != null && (
          <span>
            Δt <span className="mono">{dt.toFixed(3)} ms</span>
          </span>
        )}
      </div>
      <table className={styles.table}>
        <thead>
          <tr>
            <th />
            {roles.map((r, i) => (
              <th key={r.label}>
                {r.label}
                <span className={styles.unit}> {unitHints[i]}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>A inst</td>
            {roles.map((r) => (
              <td key={`a-${r.label}`} className="mono">
                {cell(pick(channels, r.re, quantitySide), cursorA, false)}
              </td>
            ))}
          </tr>
          <tr>
            <td>A RMS</td>
            {roles.map((r) => (
              <td key={`ar-${r.label}`} className="mono">
                {cell(pick(channels, r.re, quantitySide), cursorA, true)}
              </td>
            ))}
          </tr>
          {cursorB != null && (
            <>
              <tr>
                <td>B inst</td>
                {roles.map((r) => (
                  <td key={`b-${r.label}`} className="mono">
                    {cell(pick(channels, r.re, quantitySide), cursorB, false)}
                  </td>
                ))}
              </tr>
              <tr>
                <td>B RMS</td>
                {roles.map((r) => (
                  <td key={`br-${r.label}`} className="mono">
                    {cell(pick(channels, r.re, quantitySide), cursorB, true)}
                  </td>
                ))}
              </tr>
            </>
          )}
        </tbody>
      </table>
    </div>
  );
}
