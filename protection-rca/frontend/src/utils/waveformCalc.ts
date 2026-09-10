/** Waveform sample helpers for DR cursors / readouts. */

import type { WaveformChannelData } from '@/types';

function asArr(s: Float32Array | number[]): number[] {
  return Array.isArray(s) ? s : Array.from(s);
}

export function sampleAtTime(ch: WaveformChannelData, tUs: number): number | null {
  const times = asArr(ch.time_us);
  const samples = asArr(ch.samples);
  if (!times.length) return null;
  let best = 0;
  let bestD = Infinity;
  for (let i = 0; i < times.length; i++) {
    const d = Math.abs(times[i] - tUs);
    if (d < bestD) {
      bestD = d;
      best = i;
    }
  }
  return samples[best] ?? null;
}

export function rmsNear(ch: WaveformChannelData, tUs: number, window = 20): number | null {
  const times = asArr(ch.time_us);
  const samples = asArr(ch.samples);
  if (!times.length) return null;
  let idx = 0;
  let bestD = Infinity;
  for (let i = 0; i < times.length; i++) {
    const d = Math.abs(times[i] - tUs);
    if (d < bestD) {
      bestD = d;
      idx = i;
    }
  }
  const a = Math.max(0, idx - window);
  const b = Math.min(samples.length - 1, idx + window);
  let acc = 0;
  let n = 0;
  for (let i = a; i <= b; i++) {
    acc += samples[i] ** 2;
    n++;
  }
  return n ? Math.sqrt(acc / n) : null;
}
