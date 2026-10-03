import { describe, expect, it } from 'vitest';
import { formatEvidenceSummary } from './formatEvidenceSummary';

describe('formatEvidenceSummary', () => {
  it('formats protection sequence Expected/Observed dumps', () => {
    const raw =
      "Protection sequence order check | Expected: monotonic Pickup -> Trip -> Breaker -> Interruption Observed: {'protection_pickup': 0.301, 'protection_trip': 0.328, '52a_change': 0.381, 'current_interruption': 0.391}";
    const out = formatEvidenceSummary(raw);
    expect(out).toContain('Protection sequence order check');
    expect(out).toContain('Expected: Pickup → Trip → Breaker → Interruption');
    expect(out).toContain('Pickup 0.301 s');
    expect(out).toContain('Interrupt 0.391 s');
    expect(out).not.toContain('protection_pickup');
  });

  it('normalizes status = OK', () => {
    expect(formatEvidenceSummary('status = OK')).toBe('Status: OK');
  });
});
