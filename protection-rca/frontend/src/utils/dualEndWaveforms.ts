/**
 * SIGRA-style dual-end helpers: common timebase sync + overlay of same analogs.
 *
 * SIGRA: Paste second fault record → auto-synchronize to common time axis →
 * optionally assign N1:IB + N2:IB into one diagram.
 */
import type { WaveformChannelData, WaveformMarker } from '@/types';

/** Shift channel sample times by ``offsetUs`` (µs). */
export function shiftChannels(
  channels: WaveformChannelData[],
  offsetUs: number,
): WaveformChannelData[] {
  if (!offsetUs || !channels.length) return channels;
  return channels.map((c) => {
    const src = c.time_us;
    const n = src.length;
    const out: number[] = new Array(n);
    for (let i = 0; i < n; i++) out[i] = Number(src[i]) + offsetUs;
    return { ...c, time_us: out };
  });
}

export function shiftMarkers(markers: WaveformMarker[], offsetUs: number): WaveformMarker[] {
  if (!offsetUs || !markers.length) return markers;
  return markers.map((m) => ({ ...m, t_us: m.t_us + offsetUs }));
}

/**
 * Align remote onto local timebase.
 * Backend ``computed_sync_offset_us`` = remote_trigger − local_trigger.
 * Subtracting it from remote times puts remote trigger at local t=0 reference.
 */
export function alignRemoteToLocal(
  remoteChannels: WaveformChannelData[],
  syncOffsetUs: number | null | undefined,
): WaveformChannelData[] {
  if (syncOffsetUs == null || !Number.isFinite(syncOffsetUs)) return remoteChannels;
  return shiftChannels(remoteChannels, -syncOffsetUs);
}

export function alignRemoteMarkers(
  remoteMarkers: WaveformMarker[],
  syncOffsetUs: number | null | undefined,
): WaveformMarker[] {
  if (syncOffsetUs == null || !Number.isFinite(syncOffsetUs)) return remoteMarkers;
  return shiftMarkers(remoteMarkers, -syncOffsetUs);
}

const OVERLAY_ANALOG = /^(IA|IB|IC|IN|VA|VB|VC|IG|I0|V0)(_|$)/i;

function baseAnalogName(name: string): string | null {
  const n = String(name || '').trim().toUpperCase();
  const m = n.match(/^(IA|IB|IC|IN|VA|VB|VC|IG|I0|V0)/);
  return m ? m[1] : null;
}

/**
 * Build one SIGRA-style overlay diagram: same phase from both ends
 * (e.g. LV:IA + HV:IA) on a shared time axis.
 */
export function buildOverlayChannels(
  local: WaveformChannelData[],
  remoteAligned: WaveformChannelData[],
  leftTag: string,
  rightTag: string,
): WaveformChannelData[] {
  const pick = (list: WaveformChannelData[]) => {
    const map = new Map<string, WaveformChannelData>();
    for (const c of list) {
      if (String(c.channel.channel_type || '').toUpperCase() === 'DIGITAL') continue;
      const base = baseAnalogName(c.channel.name);
      if (!base || !OVERLAY_ANALOG.test(c.channel.name)) continue;
      if (!map.has(base)) map.set(base, c);
    }
    return map;
  };
  const L = pick(local);
  const R = pick(remoteAligned);
  const keys = ['IA', 'IB', 'IC', 'IN', 'VA', 'VB', 'VC'].filter(
    (k) => L.has(k) || R.has(k),
  );
  const out: WaveformChannelData[] = [];
  for (const k of keys) {
    const lc = L.get(k);
    const rc = R.get(k);
    if (lc) {
      out.push({
        ...lc,
        channel: {
          ...lc.channel,
          name: `${leftTag}:${k}`,
          phase: lc.channel.phase || k.slice(-1),
        },
      });
    }
    if (rc) {
      out.push({
        ...rc,
        channel: {
          ...rc.channel,
          name: `${rightTag}:${k}`,
          phase: rc.channel.phase || k.slice(-1),
        },
      });
    }
  }
  return out;
}

/** Prefixed digital tracks from both ends for cascade INTERTRIP correlation. */
export function buildCascadeDigitalStrip(
  local: WaveformChannelData[],
  remoteAligned: WaveformChannelData[],
  leftTag: string,
  rightTag: string,
): WaveformChannelData[] {
  const want = /(50BF|LBB|INTERTRIP|TRIP|52A|PICKUP)/i;
  const take = (list: WaveformChannelData[], tag: string) =>
    list
      .filter(
        (c) =>
          String(c.channel.channel_type || '').toUpperCase() === 'DIGITAL' &&
          want.test(c.channel.name),
      )
      .slice(0, 8)
      .map((c) => ({
        ...c,
        channel: { ...c.channel, name: `${tag}:${c.channel.name}` },
      }));
  return [...take(local, leftTag), ...take(remoteAligned, rightTag)];
}
