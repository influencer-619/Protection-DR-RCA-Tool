import { describe, expect, it } from 'vitest';
import {
  extractOperatedCodes,
  faultPhases,
  inferBaySchemeKind,
} from './OneLineBay';

describe('inferBaySchemeKind', () => {
  it('uses transformer template for PTR + 87G/87T', () => {
    expect(
      inferBaySchemeKind({
        bay: 'PTR',
        schemeHint: '87G PICKUP 87T PICKUP',
        distanceApplicable: false,
      }),
    ).toBe('transformer_diff');
  });

  it('uses bus template for 87B', () => {
    expect(inferBaySchemeKind({ schemeHint: '87B', bay: 'BUS' })).toBe('bus_diff');
  });

  it('uses line distance when distance applies', () => {
    expect(
      inferBaySchemeKind({
        bay: 'LINE',
        schemeHint: '21',
        distanceApplicable: true,
      }),
    ).toBe('line_distance');
  });

  it('uses feeder OC by default', () => {
    expect(inferBaySchemeKind({ bay: 'F1', schemeHint: '51' })).toBe('feeder_oc');
  });

  it('does not force 87T from PTR bay alone without differential evidence', () => {
    expect(
      inferBaySchemeKind({
        bay: 'PTR',
        schemeHint: null,
        distanceApplicable: false,
      }),
    ).toBe('feeder_oc');
  });

  it('keeps feeder OC for LBB / 50BF cascade (not distance, not 87T)', () => {
    expect(
      inferBaySchemeKind({
        bay: 'PTR',
        schemeHint: '50BF TRIP 50P TRIP 51P TRIP',
        distanceApplicable: false,
      }),
    ).toBe('feeder_oc');
  });

  it('uses line differential for 87L', () => {
    expect(
      inferBaySchemeKind({
        bay: 'LINE',
        schemeHint: '87L TRIP',
        distanceApplicable: false,
      }),
    ).toBe('line_diff');
  });

  it('does not draw distance for OC-only even on a LINE bay name', () => {
    expect(
      inferBaySchemeKind({
        bay: 'LINE',
        schemeHint: '50P TRIP 51P TRIP',
        distanceApplicable: false,
      }),
    ).toBe('feeder_oc');
  });
});

describe('extractOperatedCodes', () => {
  it('includes 50BF and OC codes in priority order', () => {
    expect(extractOperatedCodes('51P TRIP 50P TRIP 50BF TRIP')).toEqual([
      '50BF',
      '50P',
      '51P',
    ]);
  });

  it('keeps differential and distance codes', () => {
    expect(extractOperatedCodes('87T PICKUP 87G PICKUP')).toEqual(['87G', '87T']);
    expect(extractOperatedCodes('21P TRIP')).toEqual(['21P']);
  });
});

describe('faultPhases', () => {
  it('maps phase-phase and ground faults', () => {
    expect(faultPhases('AB')).toEqual(['A', 'B']);
    expect(faultPhases('AG')).toEqual(['A', 'G']);
    expect(faultPhases('BCG')).toEqual(['B', 'C', 'G']);
    expect(faultPhases('ABC')).toEqual(['A', 'B', 'C']);
    expect(faultPhases('ABCG')).toEqual(['A', 'B', 'C', 'G']);
  });

  it('ignores unknown / empty', () => {
    expect(faultPhases('UNKNOWN')).toEqual([]);
    expect(faultPhases(null)).toEqual([]);
  });
});
