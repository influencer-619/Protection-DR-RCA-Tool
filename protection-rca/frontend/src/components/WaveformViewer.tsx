import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from 'react';
import type { WaveformChannelData, WaveformMarker } from '@/types';
import { formatElectrical, unitLabel } from '@/utils/formatElectrical';
import { classifyChannelSide } from '@/utils/quantitySide';
import { sampleAtTime } from '@/utils/waveformCalc';
import styles from './WaveformViewer.module.css';

/** Warm tones — secondary (A / V) */
const SECONDARY_COLORS = ['#e07a3d', '#6bbf8a', '#5b9fd4', '#d4a017', '#3dbeb0', '#c47ac0'];
/** Cool tones — primary (kA / kV) so Both mode is visually distinct */
const PRIMARY_COLORS = ['#c084fc', '#22d3ee', '#60a5fa', '#f472b6', '#a3e635', '#fb923c'];

function phaseColorIndex(name: string): number {
  const n = name.toUpperCase().replace(/[\s-]/g, '_');
  if (/(^|_)(IA|VA|IL1|UL1|I1|V1|A)(_|$)/.test(n) || n.endsWith('_A') || n === 'A') return 0;
  if (/(^|_)(IB|VB|IL2|UL2|I2|V2|B)(_|$)/.test(n) || n.endsWith('_B') || n === 'B') return 1;
  if (/(^|_)(IC|VC|IL3|UL3|I3|V3|C)(_|$)/.test(n) || n.endsWith('_C') || n === 'C') return 2;
  if (/(^|_)(IN|VN|IG|IO|IR|N)(_|$)/.test(n) || n.includes('_PRI') && /N/.test(n)) return 3;
  return -1;
}

function analogColor(ch: WaveformChannelData, fallbackIdx: number): string {
  const side = classifyChannelSide(ch.channel.name, ch.channel.units, ch.channel.ps);
  const palette = side === 'primary' ? PRIMARY_COLORS : SECONDARY_COLORS;
  const pi = phaseColorIndex(ch.channel.name);
  if (pi >= 0) return palette[pi % palette.length];
  return palette[fallbackIdx % palette.length];
}

function sideBadge(ch: WaveformChannelData): string | null {
  if (ch.channel.channel_type === 'DIGITAL') return null;
  const side = classifyChannelSide(ch.channel.name, ch.channel.units, ch.channel.ps);
  if (side === 'primary') return 'PRI';
  if (side === 'secondary') return 'SEC';
  return null;
}

function isDigitalChannel(ch: WaveformChannelData): boolean {
  const t = String(ch.channel.channel_type || '').toUpperCase();
  if (t === 'DIGITAL' || t === 'STATUS' || t === 'BOOL' || t === 'BINARY') return true;
  const u = String(ch.channel.units || '').toUpperCase();
  return u === 'BOOL' || u === 'BOOLEAN' || u === 'STATUS' || u === 'BIT';
}

function channelGroup(ch: WaveformChannelData): 'current' | 'voltage' | 'digital' | 'other' {
  if (isDigitalChannel(ch)) return 'digital';
  const n = `${ch.channel.name} ${ch.channel.units || ''} ${ch.channel.phase || ''}`.toUpperCase();
  if (/\bI[ABC0N]?\b|CURRENT|AMP/.test(n) || (ch.channel.units || '').toUpperCase() === 'A') {
    return 'current';
  }
  if (/\bV[ABC0N]?\b|VOLT|KV/.test(n) || /V/.test((ch.channel.units || '').toUpperCase())) {
    return 'voltage';
  }
  return 'other';
}

function displayName(ch: WaveformChannelData): string {
  const n = ch.channel.name;
  if (/\./.test(n)) return n;
  const g = channelGroup(ch);
  if (g === 'current') return `${n}.inst`;
  if (g === 'voltage') return `${n}.inst`;
  return n;
}

/** Shorter legend text — drop redundant .inst suffix to reduce crowding. */
function legendLabel(ch: WaveformChannelData): string {
  return displayName(ch).replace(/\.inst$/i, '');
}

/** Left-margin label (SIGRA-style) — truncate to fit padL. */
function marginLabel(ch: WaveformChannelData, maxW: number, ctx: CanvasRenderingContext2D): string {
  let name = legendLabel(ch);
  while (name.length > 3 && ctx.measureText(name).width > maxW) {
    name = `${name.slice(0, -2)}…`;
  }
  return name;
}

type AnalogLayout = 'separate' | 'group';

interface Props {
  channels: WaveformChannelData[];
  markers?: WaveformMarker[];
  height?: number;
  /** Stretch to fill parent (pop-out / full-screen). */
  fill?: boolean;
  /** Controlled cursors (µs). */
  cursorAUs?: number | null;
  cursorBUs?: number | null;
  onCursorsChange?: (a: number | null, b: number | null) => void;
  onMarkerActivate?: (marker: WaveformMarker) => void;
  /** Hide built-in bottom readout when parent shows CursorReadout. */
  hideReadout?: boolean;
}

export function WaveformViewer({
  channels,
  markers = [],
  height = 420,
  fill = false,
  cursorAUs,
  cursorBUs,
  onCursorsChange,
  onMarkerActivate,
  hideReadout = false,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const [viewStart, setViewStart] = useState(0);
  const [viewEnd, setViewEnd] = useState(1);
  const [cursorAInner, setCursorAInner] = useState<number | null>(null);
  const [cursorBInner, setCursorBInner] = useState<number | null>(null);
  const cursorA = cursorAUs !== undefined ? cursorAUs : cursorAInner;
  const cursorB = cursorBUs !== undefined ? cursorBUs : cursorBInner;
  const setCursorA = (t: number | null) => {
    if (cursorAUs === undefined) setCursorAInner(t);
    const b = cursorBUs !== undefined ? cursorBUs : cursorBInner;
    onCursorsChange?.(t, b);
  };
  const setCursorB = (t: number | null) => {
    if (cursorBUs === undefined) setCursorBInner(t);
    const a = cursorAUs !== undefined ? cursorAUs : cursorAInner;
    onCursorsChange?.(a, t);
  };
  const [activeCursor, setActiveCursor] = useState<'A' | 'B'>('A');
  const [showRms, setShowRms] = useState(false);
  const [showAnalog, setShowAnalog] = useState(true);
  const [showDigital, setShowDigital] = useState(true);
  /** separate = one subplot per analog (DFR/SIGRA); group = overlay I then V */
  const [analogLayout, setAnalogLayout] = useState<AnalogLayout>('separate');
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [canvasHeight, setCanvasHeight] = useState(height);
  const dragRef = useRef<{ x: number; start: number; end: number } | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const scrollDragRef = useRef<{ x: number; start: number } | null>(null);

  useEffect(() => {
    if (fill) return;
    setCanvasHeight(height);
  }, [fill, height]);

  useEffect(() => {
    if (!fill) return;
    const el = bodyRef.current;
    if (!el) return;
    const apply = () => {
      const h = Math.max(320, Math.floor(el.clientHeight));
      setCanvasHeight(h);
    };
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(el);
    return () => ro.disconnect();
  }, [fill]);

  useEffect(() => {
    setSelected(new Set(channels.map((c) => c.channel.id)));
    setViewStart(0);
    setViewEnd(1);
  }, [channels]);

  const tMin = useMemo(() => {
    let m = Infinity;
    channels.forEach((c) => {
      const t = c.time_us;
      if (t.length) m = Math.min(m, Number(t[0]));
    });
    return Number.isFinite(m) ? m : 0;
  }, [channels]);

  const tMax = useMemo(() => {
    let m = -Infinity;
    channels.forEach((c) => {
      const t = c.time_us;
      if (t.length) m = Math.max(m, Number(t[t.length - 1]));
    });
    return Number.isFinite(m) ? m : 1;
  }, [channels]);

  const span = tMax - tMin || 1;
  const winStart = tMin + viewStart * span;
  const winEnd = tMin + viewEnd * span;

  const visible = useMemo(
    () =>
      channels.filter((c) => {
        if (!selected.has(c.channel.id)) return false;
        if (c.channel.channel_type === 'ANALOG' && !showAnalog) return false;
        if (c.channel.channel_type === 'DIGITAL' && !showDigital) return false;
        return true;
      }),
    [channels, selected, showAnalog, showDigital],
  );

  /** Grow plot so digital status bits are not clipped under analogs. */
  const plotHeight = useMemo(() => {
    const digCount = visible.filter((c) => channelGroup(c) === 'digital').length;
    const digH = digCount ? 18 + digCount * 22 + 24 : 0;
    const analogs = visible.filter((c) => channelGroup(c) !== 'digital');
    let analogH: number;
    if (analogLayout === 'separate') {
      // One row per channel — industry DFR / OscilloViewer style
      const rowH = analogs.length > 8 ? 64 : analogs.length > 4 ? 78 : 96;
      analogH = analogs.length * rowH + 24;
    } else {
      const bands =
        (analogs.some((c) => channelGroup(c) === 'current' || channelGroup(c) === 'other')
          ? 1
          : 0) + (analogs.some((c) => channelGroup(c) === 'voltage') ? 1 : 0) || 1;
      analogH = bands * 160 + 40;
    }
    const needed = Math.max(320, analogH + digH);
    return Math.max(canvasHeight, needed);
  }, [visible, canvasHeight, analogLayout]);

  const draw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth;
    const h = canvas.clientHeight;
    canvas.width = Math.floor(w * dpr);
    canvas.height = Math.floor(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    ctx.fillStyle = getComputedStyle(document.documentElement).getPropertyValue('--wf-bg').trim() || '#0a0e13';
    ctx.fillRect(0, 0, w, h);

    const padL = 148;
    const padR = 12;
    const padT = 10;
    const padB = 28;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;

    // grid
    ctx.strokeStyle = '#1a2230';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 10; i++) {
      const x = padL + (plotW * i) / 10;
      ctx.beginPath();
      ctx.moveTo(x, padT);
      ctx.lineTo(x, padT + plotH);
      ctx.stroke();
    }

    const winSpan = winEnd - winStart || 1;
    const xOf = (t: number) => padL + ((t - winStart) / winSpan) * plotW;

    const currents = visible.filter((c) => channelGroup(c) === 'current');
    const voltages = visible.filter((c) => channelGroup(c) === 'voltage');
    const others = visible.filter((c) => channelGroup(c) === 'other');
    const digitals = visible.filter((c) => channelGroup(c) === 'digital');
    const analogsOrdered = [...currents, ...others, ...voltages];

    const digHeaderH = digitals.length ? 18 : 0;
    const digRowH = 22;
    const digNeeded = digitals.length ? digHeaderH + digitals.length * digRowH + 10 : 0;
    const analogAvail = Math.max(120, plotH - digNeeded);

    const strokeChannel = (
      ch: WaveformChannelData,
      idx: number,
      waveTop: number,
      waveH: number,
      opts?: { zeroLine?: boolean },
    ) => {
      const samples = ch.samples;
      const times = ch.time_us;
      let ymin = Infinity;
      let ymax = -Infinity;
      for (let i = 0; i < samples.length; i++) {
        const t = Number(times[i]);
        if (t < winStart || t > winEnd) continue;
        const v = Number(samples[i]);
        ymin = Math.min(ymin, v);
        ymax = Math.max(ymax, v);
      }
      if (!Number.isFinite(ymin)) {
        ymin = -1;
        ymax = 1;
      }
      const mid = (ymin + ymax) / 2;
      const half = Math.max((ymax - ymin) / 2, 1e-6) * 1.1;
      const yOf = (v: number) => waveTop + waveH / 2 - ((v - mid) / half) * (waveH / 2) * 0.85;

      if (opts?.zeroLine && ymin <= 0 && ymax >= 0) {
        ctx.strokeStyle = '#2a3544';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(padL, yOf(0));
        ctx.lineTo(padL + plotW, yOf(0));
        ctx.stroke();
      }

      const stroke = analogColor(ch, idx);
      ctx.strokeStyle = stroke;
      ctx.lineWidth = 1.35;
      ctx.beginPath();
      let started = false;
      for (let i = 0; i < samples.length; i++) {
        const t = Number(times[i]);
        if (t < winStart - winSpan * 0.01 || t > winEnd + winSpan * 0.01) continue;
        const x = xOf(t);
        const y = yOf(Number(samples[i]));
        if (!started) {
          ctx.moveTo(x, y);
          started = true;
        } else {
          ctx.lineTo(x, y);
        }
      }
      ctx.stroke();

      if (showRms && samples.length > 8) {
        const winN = Math.max(4, Math.floor(samples.length / 40));
        ctx.strokeStyle = stroke;
        ctx.globalAlpha = 0.45;
        ctx.setLineDash([3, 3]);
        ctx.lineWidth = 1;
        ctx.beginPath();
        let startedR = false;
        for (let i = winN; i < samples.length; i++) {
          const t = Number(times[i]);
          if (t < winStart - winSpan * 0.01 || t > winEnd + winSpan * 0.01) continue;
          let acc = 0;
          for (let j = i - winN; j <= i; j++) acc += Number(samples[j]) ** 2;
          const rms = Math.sqrt(acc / (winN + 1));
          const x = xOf(t);
          const y = yOf(rms);
          if (!startedR) {
            ctx.moveTo(x, y);
            startedR = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
        ctx.stroke();
        ctx.setLineDash([]);
        ctx.globalAlpha = 1;
      }
    };

    /** One subplot per analog — name in left margin (no stacked in-plot legend). */
    const drawSeparateRow = (ch: WaveformChannelData, idx: number, bandH: number, y0: number) => {
      ctx.strokeStyle = '#2a3544';
      ctx.beginPath();
      ctx.moveTo(padL, y0);
      ctx.lineTo(padL + plotW, y0);
      ctx.stroke();

      const color = analogColor(ch, idx);
      ctx.fillStyle = color;
      ctx.fillRect(padL - 14, y0 + bandH / 2 - 5, 6, 10);

      ctx.font = '10px Consolas, Courier New, monospace';
      ctx.fillStyle = '#c5d0dc';
      ctx.textAlign = 'right';
      const name = marginLabel(ch, padL - 20, ctx);
      ctx.fillText(name, padL - 18, y0 + bandH / 2 + 3);
      ctx.textAlign = 'left';

      const unit = unitLabel(ch.channel.units, ch.channel.name);
      if (unit && unit !== '—') {
        ctx.fillStyle = '#7a8a9c';
        ctx.font = '9px Segoe UI, Tahoma, sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(unit, padL - 18, y0 + bandH / 2 + 14);
        ctx.textAlign = 'left';
      }

      strokeChannel(ch, idx, y0 + 4, Math.max(36, bandH - 8), { zeroLine: true });
    };

    /** Group overlay: I and V bands; names stay in sidebar (no in-plot legend). */
    const drawGroupBand = (
      title: string,
      chans: WaveformChannelData[],
      bandH: number,
      y0: number,
    ) => {
      ctx.strokeStyle = '#2a3544';
      ctx.beginPath();
      ctx.moveTo(padL, y0);
      ctx.lineTo(padL + plotW, y0);
      ctx.stroke();

      ctx.fillStyle = '#9aabbd';
      ctx.font = '11px Segoe UI, Tahoma, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(title, padL - 10, y0 + 14);
      ctx.textAlign = 'left';

      // Compact color ticks in left margin instead of stacked names on the plot
      chans.forEach((ch, idx) => {
        ctx.fillStyle = analogColor(ch, idx);
        ctx.fillRect(padL - 14, y0 + 22 + idx * 10, 6, 6);
      });

      chans.forEach((ch, idx) => strokeChannel(ch, idx, y0 + 8, Math.max(40, bandH - 12)));
    };

    let yCursor = padT;

    if (analogLayout === 'separate' && analogsOrdered.length) {
      const gap = 4;
      const rowH = Math.max(
        56,
        (analogAvail - (analogsOrdered.length - 1) * gap) / analogsOrdered.length,
      );
      analogsOrdered.forEach((ch, idx) => {
        drawSeparateRow(ch, idx, rowH, yCursor);
        yCursor += rowH + gap;
      });
    } else {
      const currentBandChans = [...currents, ...others];
      const bands = (currentBandChans.length ? 1 : 0) + (voltages.length ? 1 : 0) || 1;
      const analogBandH = Math.max(88, (analogAvail - (bands - 1) * 8) / bands);
      if (currentBandChans.length) {
        drawGroupBand('Current', currentBandChans, analogBandH, yCursor);
        yCursor += analogBandH + 8;
      }
      if (voltages.length) {
        drawGroupBand('Voltage', voltages, analogBandH, yCursor);
        yCursor += analogBandH + 8;
      }
    }

    if (digitals.length) {
      ctx.fillStyle = '#9aabbd';
      ctx.font = '11px Segoe UI, Tahoma, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText('Digitals', padL - 10, yCursor + 12);
      ctx.textAlign = 'left';

      digitals.forEach((ch, idx) => {
        const yBase = yCursor + digHeaderH + 12 + idx * digRowH;
        const samples = ch.samples;
        const times = ch.time_us;
        ctx.strokeStyle = '#3dbeb0';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        let prev = 0;
        let first = true;
        for (let i = 0; i < samples.length; i++) {
          const t = Number(times[i]);
          if (t < winStart || t > winEnd) continue;
          const v = Number(samples[i]) ? 1 : 0;
          const x = xOf(t);
          const y = yBase - v * 10;
          if (first) {
            ctx.moveTo(x, yBase - prev * 10);
            first = false;
          }
          if (v !== prev) {
            ctx.lineTo(x, yBase - prev * 10);
            ctx.lineTo(x, y);
          } else {
            ctx.lineTo(x, y);
          }
          prev = v;
        }
        ctx.stroke();

        ctx.font = '10px Consolas, Courier New, monospace';
        ctx.fillStyle = '#9aabbd';
        const name = marginLabel(ch, padL - 12, ctx);
        ctx.textAlign = 'right';
        ctx.fillText(name, padL - 10, yBase - 1);
        ctx.textAlign = 'left';
      });
    }

    // markers — lines for all; on-plot labels only for key events (full list is below)
    const KEY_LABELS: { match: RegExp; text: string; priority: number }[] = [
      { match: /^trigger$/i, text: 'Trigger', priority: 1 },
      { match: /fault\s*inception/i, text: 'Fault', priority: 2 },
      { match: /^trip$/i, text: 'Trip', priority: 3 },
      { match: /^pickup$/i, text: 'Pickup', priority: 4 },
      { match: /record\s*start/i, text: 'Start', priority: 5 },
    ];

    const keyInfo = (label: string) => {
      const s = (label || '').trim();
      for (const k of KEY_LABELS) {
        if (k.match.test(s)) return k;
      }
      return null;
    };

    const visibleMarkers = markers
      .filter((m) => m.t_us >= winStart && m.t_us <= winEnd)
      .sort((a, b) => a.t_us - b.t_us);

    const clusterTolUs = Math.max(2000, winSpan * 0.008);
    type Cluster = { t_us: number; color: string; label?: string; priority: number };
    const clusters: Cluster[] = [];
    for (const m of visibleMarkers) {
      const color = m.color || '#d64545';
      const key = keyInfo(m.label || '');
      const last = clusters[clusters.length - 1];
      if (last && Math.abs(m.t_us - last.t_us) <= clusterTolUs) {
        last.t_us = (last.t_us + m.t_us) / 2;
        if (key && (last.priority === 0 || key.priority < last.priority)) {
          last.label = key.text;
          last.priority = key.priority;
          last.color = m.color || last.color;
        }
      } else {
        clusters.push({
          t_us: m.t_us,
          color,
          label: key?.text,
          priority: key?.priority ?? 0,
        });
      }
    }

    // Marker / cursor chips sit near the bottom of the plot.
    const usedLabelBoxes: { x: number; y: number; w: number; h: number }[] = [];
    const placeChip = (
      text: string,
      xAnchor: number,
      color: string,
      font: string,
      preferY: number,
    ) => {
      ctx.font = font;
      const tw = ctx.measureText(text).width + 8;
      const th = 13;
      let labelX = xAnchor + 4;
      if (labelX + tw > padL + plotW - 2) labelX = xAnchor - tw - 4;
      let labelY = preferY;
      for (let i = 0; i < 8; i++) {
        const hit = usedLabelBoxes.some(
          (b) =>
            labelX < b.x + b.w &&
            labelX + tw > b.x &&
            labelY - th < b.y &&
            labelY > b.y - b.h,
        );
        if (!hit) break;
        labelY -= th + 2;
      }
      if (labelY < padT + 12) labelY = padT + 12;
      ctx.fillStyle = 'rgba(10, 14, 19, 0.88)';
      ctx.fillRect(labelX - 2, labelY - 10, tw, th);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.strokeRect(labelX - 2, labelY - 10, tw, th);
      ctx.fillStyle = color;
      ctx.fillText(text, labelX + 2, labelY);
      usedLabelBoxes.push({ x: labelX - 2, y: labelY, w: tw, h: th });
    };

    clusters.forEach((cl) => {
      const x = xOf(cl.t_us);
      ctx.strokeStyle = cl.color;
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 3]);
      ctx.beginPath();
      ctx.moveTo(x, padT);
      ctx.lineTo(x, padT + plotH);
      ctx.stroke();
      ctx.setLineDash([]);

      if (!cl.label) return;
      placeChip(cl.label, x, cl.color, '10px Segoe UI, Tahoma, sans-serif', padT + plotH - 16);
    });

    // cursors A / B — time chip only (channel values live in the bottom readout)
    const drawCursor = (t: number | null, color: string, tag: string) => {
      if (t == null || t < winStart || t > winEnd) return;
      const x = xOf(t);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.25;
      ctx.beginPath();
      ctx.moveTo(x, padT);
      ctx.lineTo(x, padT + plotH);
      ctx.stroke();
      placeChip(
        `${tag} ${((t - tMin) / 1000).toFixed(2)} ms`,
        x,
        color,
        '10px Consolas, Courier New, monospace',
        padT + plotH - (tag === 'A' ? 32 : 16),
      );
    };
    drawCursor(cursorA, '#e8c547', 'A');
    drawCursor(cursorB, '#7ec8e3', 'B');

    // time axis
    ctx.fillStyle = '#7a8a9c';
    ctx.font = '10px Consolas, Courier New, monospace';
    for (let i = 0; i <= 5; i++) {
      const t = winStart + (winSpan * i) / 5;
      const x = xOf(t);
      ctx.fillText(`${((t - tMin) / 1000).toFixed(0)}`, x - 8, padT + plotH + 16);
    }
    ctx.fillText('ms', w - 28, h - 8);
  }, [visible, winStart, winEnd, markers, cursorA, cursorB, tMin, plotHeight, showRms, analogLayout]);

  useEffect(() => {
    draw();
  }, [draw]);

  useEffect(() => {
    const onResize = () => draw();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [draw]);

  const toggleChannel = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const onWheel = (e: ReactWheelEvent) => {
    e.preventDefault();
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const frac = (e.clientX - rect.left) / rect.width;
    const zoomFactor = e.deltaY > 0 ? 1.15 : 0.87;
    let newSpan = (viewEnd - viewStart) * zoomFactor;
    newSpan = Math.min(1, Math.max(0.002, newSpan));
    let newStart = viewStart + frac * (viewEnd - viewStart) - frac * newSpan;
    newStart = Math.max(0, Math.min(1 - newSpan, newStart));
    setViewStart(newStart);
    setViewEnd(newStart + newSpan);
  };

  const onPointerDown = (e: ReactPointerEvent) => {
    if (e.button === 1 || e.shiftKey) {
      dragRef.current = { x: e.clientX, start: viewStart, end: viewEnd };
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
      return;
    }
    // Click near a marker → snap active cursor
    if (markers.length && canvasRef.current) {
      const rect = canvasRef.current.getBoundingClientRect();
      const padL = 148;
      const padR = 12;
      const plotW = rect.width - padL - padR;
      const rel = (e.clientX - rect.left - padL) / plotW;
      const t = winStart + Math.max(0, Math.min(1, rel)) * (winEnd - winStart);
      const hit = markers.find((m) => Math.abs(m.t_us - t) < (winEnd - winStart) * 0.012);
      if (hit) {
        snapCursorToMarker(hit);
        return;
      }
    }
  };

  const onPointerMove = (e: ReactPointerEvent) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const rect = canvas.getBoundingClientRect();
    const padL = 148;
    const padR = 12;
    const plotW = rect.width - padL - padR;
    const rel = (e.clientX - rect.left - padL) / plotW;
    const t = winStart + Math.max(0, Math.min(1, rel)) * (winEnd - winStart);
    if (activeCursor === 'A') setCursorA(t);
    else setCursorB(t);

    if (dragRef.current) {
      const dx = e.clientX - dragRef.current.x;
      const frac = dx / plotW;
      const spanV = dragRef.current.end - dragRef.current.start;
      let ns = dragRef.current.start - frac * spanV;
      ns = Math.max(0, Math.min(1 - spanV, ns));
      setViewStart(ns);
      setViewEnd(ns + spanV);
    }
  };

  const onPointerUp = () => {
    dragRef.current = null;
  };

  const resetZoom = () => {
    setViewStart(0);
    setViewEnd(1);
  };

  const zoomToCursors = () => {
    if (cursorA == null || cursorB == null) return;
    const lo = Math.min(cursorA, cursorB);
    const hi = Math.max(cursorA, cursorB);
    const pad = Math.max((hi - lo) * 0.08, span * 0.002);
    const a = Math.max(tMin, lo - pad);
    const b = Math.min(tMax, hi + pad);
    const s = tMax - tMin || 1;
    setViewStart((a - tMin) / s);
    setViewEnd((b - tMin) / s);
  };

  const snapCursorToMarker = (m: WaveformMarker) => {
    if (activeCursor === 'A') setCursorA(m.t_us);
    else setCursorB(m.t_us);
    onMarkerActivate?.(m);
  };

  const zoomed = viewEnd - viewStart < 0.999;
  const viewSpan = Math.max(0.002, viewEnd - viewStart);

  const panTo = (startFrac: number) => {
    const span = viewEnd - viewStart;
    const ns = Math.max(0, Math.min(1 - span, startFrac));
    setViewStart(ns);
    setViewEnd(ns + span);
  };

  const onScrollPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!zoomed) return;
    const track = scrollRef.current;
    if (!track) return;
    const rect = track.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const thumbW = Math.max(24, viewSpan * rect.width);
    const thumbLeft = viewStart * rect.width;
    let startAtDown = viewStart;
    // Click outside thumb → jump so thumb centers on click
    if (x < thumbLeft || x > thumbLeft + thumbW) {
      startAtDown = Math.max(0, Math.min(1 - viewSpan, x / rect.width - viewSpan / 2));
      panTo(startAtDown);
    }
    scrollDragRef.current = { x: e.clientX, start: startAtDown };
    track.setPointerCapture(e.pointerId);
    e.preventDefault();
  };

  const onScrollPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (!scrollDragRef.current || !scrollRef.current) return;
    const rect = scrollRef.current.getBoundingClientRect();
    const dx = e.clientX - scrollDragRef.current.x;
    panTo(scrollDragRef.current.start + dx / rect.width);
  };

  const onScrollPointerUp = () => {
    scrollDragRef.current = null;
  };

  const onZoomSlider = (e: React.ChangeEvent<HTMLInputElement>) => {
    // 0 = fully zoomed out (span 1), 100 = max zoom (span 0.002)
    const z = Number(e.target.value); // 0..100
    const minSpan = 0.002;
    const span = minSpan + (1 - minSpan) * (1 - z / 100);
    const mid = (viewStart + viewEnd) / 2;
    let ns = mid - span / 2;
    ns = Math.max(0, Math.min(1 - span, ns));
    setViewStart(ns);
    setViewEnd(ns + span);
  };

  const zoomPct = Math.round((1 - (viewSpan - 0.002) / (1 - 0.002)) * 100);
  const deltaUs =
    cursorA != null && cursorB != null ? Math.abs(cursorB - cursorA) : null;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      const stepFrac = e.shiftKey ? 0.02 : 0.005;
      const spanWin = winEnd - winStart || 1;
      if (e.key === 'a' || e.key === 'A') {
        setActiveCursor('A');
        e.preventDefault();
      } else if (e.key === 'b' || e.key === 'B') {
        setActiveCursor('B');
        e.preventDefault();
      } else if (e.key === 'z' || e.key === 'Z') {
        zoomToCursors();
        e.preventDefault();
      } else if (e.key === 'r' || e.key === 'R') {
        resetZoom();
        e.preventDefault();
      } else if (e.key === 'm' || e.key === 'M') {
        if (!markers.length) return;
        let best = markers[0];
        let bestD = Infinity;
        const ref = activeCursor === 'A' ? cursorA : cursorB;
        for (const m of markers) {
          const d = ref == null ? 0 : Math.abs(m.t_us - ref);
          if (d < bestD) {
            bestD = d;
            best = m;
          }
        }
        if (activeCursor === 'A') setCursorA(best.t_us);
        else setCursorB(best.t_us);
        onMarkerActivate?.(best);
        e.preventDefault();
      } else if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
        const dir = e.key === 'ArrowLeft' ? -1 : 1;
        const cur = activeCursor === 'A' ? cursorA : cursorB;
        const base = cur ?? (winStart + winEnd) / 2;
        const next = Math.max(tMin, Math.min(tMax, base + dir * stepFrac * spanWin));
        if (activeCursor === 'A') setCursorA(next);
        else setCursorB(next);
        e.preventDefault();
      } else if (e.key === '[' || e.key === ']') {
        const dir = e.key === '[' ? -1 : 1;
        panTo(viewStart + dir * stepFrac);
        e.preventDefault();
      } else if (e.key === '1' || e.key === '2' || e.key === '3') {
        const n = Number(e.key);
        const analogs = channels.filter((c) => c.channel.channel_type === 'ANALOG');
        if (analogs[n - 1]) {
          setSelected(new Set([analogs[n - 1].channel.id]));
          e.preventDefault();
        }
      } else if (e.key === '0') {
        setSelected(new Set(channels.map((c) => c.channel.id)));
        e.preventDefault();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [
    activeCursor,
    cursorA,
    cursorB,
    markers,
    winStart,
    winEnd,
    viewStart,
    tMin,
    tMax,
    channels,
    onMarkerActivate,
  ]);

  return (
    <div className={`${styles.viewer}${fill ? ` ${styles.fill}` : ''}`} tabIndex={0}>
      <div className={styles.toolbar}>
        <div className={styles.toggles}>
          <label>
            <input type="checkbox" checked={showAnalog} onChange={(e) => setShowAnalog(e.target.checked)} />
            Analog
          </label>
          <label>
            <input type="checkbox" checked={showDigital} onChange={(e) => setShowDigital(e.target.checked)} />
            Digital
          </label>
          <label>
            <input type="checkbox" checked={showRms} onChange={(e) => setShowRms(e.target.checked)} />
            RMS overlay
          </label>
          <label>
            Layout{' '}
            <select
              value={analogLayout}
              onChange={(e) => setAnalogLayout(e.target.value as AnalogLayout)}
              style={{ marginLeft: 4 }}
              title="Separate = one subplot per analog (recommended). Group = overlay currents / voltages."
            >
              <option value="separate">Separate channels</option>
              <option value="group">Group I / V</option>
            </select>
          </label>
          <label>
            Cursor{' '}
            <select
              value={activeCursor}
              onChange={(e) => setActiveCursor(e.target.value as 'A' | 'B')}
              style={{ marginLeft: 4 }}
            >
              <option value="A">A</option>
              <option value="B">B</option>
            </select>
          </label>
        </div>
        <div className={styles.hint}>
          A/B cursor · ←/→ nudge · Z zoom A–B · M snap marker · [ ] pan · 1–3 solo · 0 all
        </div>
        <label className={styles.zoomLabel}>
          Zoom
          <input
            type="range"
            className={styles.zoomRange}
            min={0}
            max={100}
            step={1}
            value={zoomPct}
            onChange={onZoomSlider}
            title="Zoom level"
          />
        </label>
        <button type="button" className="btn btn-sm" onClick={zoomToCursors} disabled={cursorA == null || cursorB == null}>
          Zoom to A–B
        </button>
        <button type="button" className="btn btn-sm" onClick={resetZoom}>
          Reset zoom
        </button>
      </div>
      <div className={styles.body} ref={bodyRef}>
        <aside className={styles.channels}>
          <div className={styles.chTitle}>Channels</div>
          <div className={styles.colorKey}>
            <span>
              <i className={styles.keySec} /> Secondary
            </span>
            <span>
              <i className={styles.keyPri} /> Primary
            </span>
          </div>
          {channels.map((c, idx) => {
            const badge = sideBadge(c);
            const color =
              c.channel.channel_type === 'ANALOG' ? analogColor(c, idx) : 'var(--text-muted)';
            return (
              <label key={c.channel.id} className={styles.chItem}>
                <input
                  type="checkbox"
                  checked={selected.has(c.channel.id)}
                  onChange={() => toggleChannel(c.channel.id)}
                />
                <span className={styles.swatch} style={{ background: color }} aria-hidden />
                <span className="mono">
                  {c.channel.name}
                  {(() => {
                    const u = unitLabel(c.channel.units, c.channel.name);
                    return u !== '—' ? <span className={styles.chType}> {u}</span> : null;
                  })()}
                  {badge && (
                    <span
                      className={badge === 'PRI' ? styles.badgePri : styles.badgeSec}
                      title={badge === 'PRI' ? 'Primary (kA/kV)' : 'Secondary (A/V)'}
                    >
                      {badge}
                    </span>
                  )}
                  <span className={styles.chType}>{c.channel.channel_type[0]}</span>
                </span>
              </label>
            );
          })}
        </aside>
        <div className={styles.plotCol}>
          <canvas
            ref={canvasRef}
            className={styles.canvas}
            style={{ height: plotHeight, minHeight: fill ? '100%' : undefined }}
            onWheel={onWheel}
            onPointerDown={onPointerDown}
            onPointerMove={onPointerMove}
            onPointerUp={onPointerUp}
            onPointerLeave={onPointerUp}
          />
          {zoomed && (
            <div
              className={styles.scrollTrack}
              ref={scrollRef}
              onPointerDown={onScrollPointerDown}
              onPointerMove={onScrollPointerMove}
              onPointerUp={onScrollPointerUp}
              onPointerCancel={onScrollPointerUp}
              title="Drag to pan through the record"
            >
              <div
                className={styles.scrollThumb}
                style={{
                  left: `${viewStart * 100}%`,
                  width: `${Math.max(3, viewSpan * 100)}%`,
                }}
              />
            </div>
          )}
        </div>
      </div>
      {!hideReadout && (cursorA != null || cursorB != null) && (
        <div className={styles.readout}>
          <div>
            {cursorA != null && (
              <>
                A:{' '}
                <span className="mono">{((cursorA - tMin) / 1000).toFixed(3)} ms</span>
              </>
            )}
            {cursorA != null && cursorB != null ? ' · ' : null}
            {cursorB != null && (
              <>
                B:{' '}
                <span className="mono">{((cursorB - tMin) / 1000).toFixed(3)} ms</span>
              </>
            )}
            {deltaUs != null && (
              <>
                {' · '}
                Δt: <span className="mono">{(deltaUs / 1000).toFixed(3)} ms</span>
              </>
            )}
            {' · '}
            Window:{' '}
            <span className="mono">
              {((winStart - tMin) / 1000).toFixed(2)} – {((winEnd - tMin) / 1000).toFixed(2)} ms
            </span>
            {zoomed ? (
              <>
                {' · '}
                <span className="mono">zoom {zoomPct}%</span>
              </>
            ) : null}
          </div>
          <div className={styles.readoutValues}>
            {visible
              .filter((c) => !isDigitalChannel(c))
              .map((ch, idx) => {
                const a =
                  cursorA != null
                    ? formatElectrical(sampleAtTime(ch, cursorA), ch.channel.units, {
                        nameHint: ch.channel.name,
                        digits: 3,
                      })
                    : null;
                const b =
                  cursorB != null
                    ? formatElectrical(sampleAtTime(ch, cursorB), ch.channel.units, {
                        nameHint: ch.channel.name,
                        digits: 3,
                      })
                    : null;
                return (
                  <span key={ch.channel.id || `${ch.channel.name}-${idx}`} className={styles.readoutCh}>
                    <i style={{ background: analogColor(ch, idx) }} />
                    <span className="mono">{legendLabel(ch)}</span>
                    {a != null && (
                      <span className="mono" style={{ color: '#e8c547' }} title="At cursor A">
                        {a}
                      </span>
                    )}
                    {a != null && b != null && <span className={styles.readoutSep}>/</span>}
                    {b != null && (
                      <span className="mono" style={{ color: '#7ec8e3' }} title="At cursor B">
                        {b}
                      </span>
                    )}
                  </span>
                );
              })}
          </div>
          {visible.some(isDigitalChannel) && (
            <div className={styles.readoutStatus}>
              <span className={styles.readoutStatusLabel}>Status</span>
              {visible.filter(isDigitalChannel).map((ch, idx) => {
                const fmt = (t: number | null) => {
                  if (t == null) return null;
                  const v = sampleAtTime(ch, t);
                  if (v == null || Number.isNaN(Number(v))) return '—';
                  return Number(v) > 0.5 ? '1' : '0';
                };
                const a = fmt(cursorA);
                const b = fmt(cursorB);
                return (
                  <span
                    key={ch.channel.id || `dig-${ch.channel.name}-${idx}`}
                    className={styles.readoutCh}
                  >
                    <i style={{ background: '#3dbeb0' }} />
                    <span className="mono">{legendLabel(ch)}</span>
                    {a != null && (
                      <span
                        className="mono"
                        style={{ color: a === '1' ? '#e8c547' : '#7a8a9c' }}
                        title="At cursor A"
                      >
                        {a}
                      </span>
                    )}
                    {a != null && b != null && <span className={styles.readoutSep}>/</span>}
                    {b != null && (
                      <span
                        className="mono"
                        style={{ color: b === '1' ? '#7ec8e3' : '#7a8a9c' }}
                        title="At cursor B"
                      >
                        {b}
                      </span>
                    )}
                  </span>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
