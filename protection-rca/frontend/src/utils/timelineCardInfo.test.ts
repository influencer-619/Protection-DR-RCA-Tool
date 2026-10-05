import { describe, expect, it } from 'vitest';
import type { TimelineEntry } from '@/types';
import { buildTimelineCardInfo, matchTimelineType, timelineEventTitle } from './timelineCardInfo';

function entry(partial: Partial<TimelineEntry>): TimelineEntry {
  return {
    id: '1',
    event_id: 'e',
    sequence: 1,
    event_type: 'protection_pickup',
    ...partial,
  };
}

describe('timelineCardInfo', () => {
  it('titles protection events for engineers', () => {
    expect(timelineEventTitle('PROTECTION_TRIP')).toBe('Protection trip');
    expect(timelineEventTitle('52a_change')).toBe('Breaker 52a status change');
  });

  it('formats digital trip from payload metadata', () => {
    const info = buildTimelineCardInfo(
      entry({
        event_type: 'PROTECTION_TRIP',
        source: 'digital:TRIP_CMD',
        label: 'protection_trip',
        description: '{"from": 0, "to": 1, "channel": "TRIP_CMD"', // truncated on purpose
        payload: {
          event_type: 'protection_trip',
          source: 'digital:TRIP_CMD',
          metadata: {
            from: 0,
            to: 1,
            channel: 'TRIP_CMD',
            target_role: 'TRIP',
          },
        },
      }),
    );
    expect(info.summary.toLowerCase()).toContain('trip');
    expect(info.facts.some((f) => f.label === 'Channel' && f.value === 'TRIP_CMD')).toBe(true);
    expect(info.facts.some((f) => f.label === 'State' && f.value.includes('0 → 1'))).toBe(true);
    expect(info.summary).not.toContain('{');
  });

  it('formats analog voltage change with units', () => {
    const info = buildTimelineCardInfo(
      entry({
        event_type: 'VOLTAGE_CHANGE',
        source: 'analog:VA',
        payload: {
          metadata: {
            baseline_rms: 63.4592452770378,
            threshold: 53.94035848548213,
          },
        },
      }),
    );
    expect(info.title).toMatch(/Voltage/i);
    const base = info.facts.find((f) => f.label === 'Baseline');
    expect(base?.value).toMatch(/V$/);
    expect(base?.value).not.toMatch(/63\.4592452770378/);
  });

  it('matches event types case-insensitively', () => {
    expect(matchTimelineType('PROTECTION_PICKUP', ['protection_pickup'])).toBe(true);
    expect(matchTimelineType('52A_CHANGE', ['52a_change'])).toBe(true);
  });
});
