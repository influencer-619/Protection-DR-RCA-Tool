import { describe, expect, it } from 'vitest';
import { formatCheckName, formatFindingValue } from './findingValue';

describe('formatFindingValue', () => {
  it('unwraps value= dumps and formats a protection sequence', () => {
    expect(
      formatFindingValue({
        value: "{'protection_pickup': 0.301, 'protection_trip': 0.306, '52a_change': 0.381, 'current_interruption': 0.391}",
      }),
    ).toBe('Pickup 0.301 s  →  Trip 0.306 s  →  Breaker (52a) 0.381 s  →  Interrupt 0.391 s');
  });

  it('formats expected sequence text', () => {
    expect(formatFindingValue({ value: 'monotonic Pickup → Trip → Breaker → Interruption' })).toBe(
      'Pickup → Trip → Breaker → Interruption',
    );
  });

  it('formats enabled/pickup pairs', () => {
    expect(formatFindingValue({ value: 'enabled=FALSE, pickup=TRUE' })).toBe('Enabled: no · Pickup: yes');
  });

  it('formats structured times_s', () => {
    expect(
      formatFindingValue({
        times_s: { protection_pickup: 0.301, protection_trip: 0.306 },
      }),
    ).toBe('Pickup 0.301 s  →  Trip 0.306 s');
  });
});

describe('formatCheckName', () => {
  it('titles protection_sequence', () => {
    expect(formatCheckName('protection_sequence')).toBe('Protection sequence');
  });
});
