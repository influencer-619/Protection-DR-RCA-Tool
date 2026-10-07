import { describe, expect, it } from 'vitest';
import { inferBaySchemeKind } from './OneLineBay';

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
});
