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
import { unitLabel } from '@/utils/formatElectrical';
import { classifyChannelSide } from '@/utils/quantitySide';
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

function channelGroup(ch: WaveformChannelData): 'current' | 'voltage' | 'digital' | 'other' {
  if (ch.channel.channel_type === 'DIGITAL') return 'digital';
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

    const padL = 118;
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
    for (let i = 0; i <= 8; i++) {
      const y = padT + (plotH * i) / 8;
      ctx.beginPath();
      ctx.moveTo(padL, y);
      ctx.lineTo(padL + plotW, y);
      ctx.stroke();
    }

    const winSpan = winEnd - winStart || 1;
    const xOf = (t: number) => padL + ((t - winStart) / winSpan) * plotW;

    const currents = visible.filter((c) => channelGroup(c) === 'current');
    const voltages = visible.filter((c) => channelGroup(c) === 'voltage');
    const others = visible.filter((c) => channelGroup(c) === 'other');
    const digitals = visible.filter((c) => channelGroup(c) === 'digital');

    const digHeaderH = digitals.length ? 18 : 0;
    const digRowH = 22;
    const digNeeded = digitals.length ? digHeaderH + digitals.length * digRowH + 10 : 0;
    const analogAvail = Math.max(120, plotH - digNeeded);
    const analogBands =
      (currents.length || others.length ? 1 : 0) + (voltages.length ? 1 : 0) || 1;
    const analogBandH = Math.max(72, (analogAvail - (analogBands - 1) * 8) / analogBands);
    const legendStrip = 18;

    let yCursor = padT;
    const drawAnalogBand = (
      label: string,
      chans: WaveformChannelData[],
      bandH: number,
      y0: number,
    ) => {
      ctx.strokeStyle = '#2a3544';
      ctx.beginPath();
      ctx.moveTo(padL, y0);
      ctx.lineTo(padL + plotW, y0);
      ctx.stroke();

      // Band title in left margin (avoids plot clutter)
      ctx.fillStyle = '#9aabbd';
      ctx.font = '11px Segoe UI, Tahoma, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(label, padL - 8, y0 + 14);
      ctx.textAlign = 'left';

      // Color legend across top of band (measured spacing, no pile-up)
      ctx.font = '11px Consolas, Courier New, monospace';
      let lx = padL + 6;
      const ly = y0 + 13;
      chans.forEach((ch, idx) => {
        const name = displayName(ch);
        const color = analogColor(ch, idx);
        const tw = ctx.measureText(name).width;
        if (lx + tw + 14 > padL + plotW - 4) {
          return; // skip overflow rather than overlap
        }
        ctx.fillStyle = color;
        ctx.fillRect(lx, ly - 7, 8, 8);
        ctx.fillText(name, lx + 11, ly);
        lx += tw + 22;
      });

      const waveTop = y0 + legendStrip;
      const waveH = Math.max(40, bandH - legendStrip);

      chans.forEach((ch, idx) => {
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

        const stroke = analogColor(ch, idx);
        ctx.strokeStyle = stroke;
        ctx.lineWidth = 1.25;
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

        // Optional 1-cycle RMS envelope (approx, sliding window ~1/50 of span samples)
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
      });
    };

    if (currents.length || others.length) {
      drawAnalogBand('Current', [...currents, ...others], analogBandH, yCursor);
      yCursor += analogBandH + 8;
    }
    if (voltages.length) {
      drawAnalogBand('Voltage', voltages, analogBandH, yCursor);
      yCursor += analogBandH + 8;
    }

    if (digitals.length) {
      ctx.fillStyle = '#9aabbd';
      ctx.font = '11px Segoe UI, Tahoma, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText('Digitals', padL - 8, yCursor + 12);
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

        // Name in left margin, truncated to fit
        const raw = displayName(ch);
        ctx.font = '10px Consolas, Courier New, monospace';
        ctx.fillStyle = '#9aabbd';
        let name = raw;
        while (name.length > 4 && ctx.measureText(name).width > padL - 10) {
          name = `${name.slice(0, -2)}…`;
        }
        ctx.textAlign = 'right';
        ctx.fillText(name, padL - 8, yBase - 1);
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

    // Avoid stacking key labels that sit on nearly the same x
    const usedLabelBoxes: { x: number; y: number; w: number }[] = [];
    ctx.font = '10px Segoe UI, Tahoma, sans-serif';

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
      const tw = ctx.measureText(cl.label).width + 6;
      let labelX = x + 4;
      if (labelX + tw > padL + plotW - 2) labelX = x - tw - 4;
      let labelY = padT + 12;
      for (let i = 0; i < 6; i++) {
        const hit = usedLabelBoxes.some(
          (b) => labelX < b.x + b.w && labelX + tw > b.x && Math.abs(labelY - b.y) < 12,
        );
        if (!hit) break;
        labelY += 12;
      }
      ctx.fillStyle = 'rgba(15, 22, 32, 0.75)';
      ctx.fillRect(labelX - 2, labelY - 10, tw, 12);
      ctx.fillStyle = cl.color;
      ctx.fillText(cl.label, labelX, labelY);
      usedLabelBoxes.push({ x: labelX - 2, y: labelY, w: tw });
    });

    // cursors A / B
    const drawCursor = (t: number | null, color: string, tag: string) => {
      if (t == null || t < winStart || t > winEnd) return;
      const x = xOf(t);
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x, padT);
      ctx.lineTo(x, padT + plotH);
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.font = '10px Consolas, Courier New, monospace';
      const ct = `${tag} ${((t - tMin) / 1000).toFixed(2)} ms`;
      const tw = ctx.measureText(ct).width;
      let cx = x + 4;
      if (cx + tw > padL + plotW - 4) cx = x - tw - 4;
      ctx.fillText(ct, cx, padT + (tag === 'A' ? 12 : 24));
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
  }, [visible, winStart, winEnd, markers, cursorA, cursorB, tMin, canvasHeight, showRms]);

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
      const padL = 118;
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
    const padL = 118;
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
            style={{ height: fill ? '100%' : canvasHeight }}
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
          {cursorA != null && (
            <>
              A: <span className="mono">{(cursorA / 1000).toFixed(3)} ms</span>
            </>
          )}
          {cursorA != null && cursorB != null ? ' · ' : null}
          {cursorB != null && (
            <>
              B: <span className="mono">{(cursorB / 1000).toFixed(3)} ms</span>
            </>
          )}
          {deltaUs != null && (
            <>
              {' · '}
              Δt: <span className="mono">{(deltaUs / 1000).toFixed(3)} ms</span>
              {' ('}
              <span className="mono">{deltaUs.toFixed(0)} µs</span>
              {')'}
            </>
          )}
          {' · '}
          Window:{' '}
          <span className="mono">
            {(winStart / 1000).toFixed(2)} – {(winEnd / 1000).toFixed(2)} ms
          </span>
          {zoomed ? (
            <>
              {' · '}
              <span className="mono">zoom {zoomPct}%</span>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
}
