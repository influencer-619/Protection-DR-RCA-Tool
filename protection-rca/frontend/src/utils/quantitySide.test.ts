import { describe, expect, it } from 'vitest';
import {
  classifyChannelSide,
  detectAvailableSides,
  filterMeasurementsBySide,
  filterWaveformChannelsBySide,
} from '@/utils/quantitySide';

describe('quantitySide', () => {
  it('classifies secondary and primary by name/unit/ps', () => {
    expect(classifyChannelSide('IA', 'A', 'S')).toBe('secondary');
    expect(classifyChannelSide('VA', 'V')).toBe('secondary');
    expect(classifyChannelSide('IA_PRI', 'kA')).toBe('primary');
    expect(classifyChannelSide('VA_PRI', 'kV', 'P')).toBe('primary');
  });

  it('detects dual-side COMTRADE packs', () => {
    const sides = detectAvailableSides([
      { name: 'IA', units: 'A' },
      { name: 'VA', units: 'V' },
      { name: 'IA_PRI', units: 'kA' },
      { name: 'VA_PRI', units: 'kV' },
    ]);
    expect(sides.hasPrimary).toBe(true);
    expect(sides.hasSecondary).toBe(true);
  });

  it('filters waveform channels by side', () => {
    const channels = [
      { channel: { name: 'IA', units: 'A', channel_type: 'ANALOG' as const } },
      { channel: { name: 'IA_PRI', units: 'kA', channel_type: 'ANALOG' as const } },
      { channel: { name: 'TRIP', units: null, channel_type: 'DIGITAL' as const } },
    ];
    const sec = filterWaveformChannelsBySide(channels, 'secondary');
    expect(sec.map((c) => c.channel.name)).toEqual(['IA', 'TRIP']);
    const pri = filterWaveformChannelsBySide(channels, 'primary');
    expect(pri.map((c) => c.channel.name)).toEqual(['IA_PRI', 'TRIP']);
  });

  it('filters electrical measurements by side', () => {
    const meas = [
      { quantity: 'IA_rms', unit: 'A' },
      { quantity: 'IA_PRI_rms', unit: 'kA' },
      { quantity: 'I0', unit: 'A' },
      { quantity: 'Z_AB', unit: 'ohm' },
    ];
    const sec = filterMeasurementsBySide(meas, 'secondary');
    expect(sec.map((m) => m.quantity)).toEqual(['IA_rms', 'I0', 'Z_AB']);
    const pri = filterMeasurementsBySide(meas, 'primary');
    expect(pri.map((m) => m.quantity)).toEqual(['IA_PRI_rms']);
  });
});
