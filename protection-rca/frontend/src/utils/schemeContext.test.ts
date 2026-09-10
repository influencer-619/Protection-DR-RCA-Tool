import { describe, expect, it } from 'vitest';
import { isDistanceApplicable } from '@/utils/schemeContext';
import type { FaultClassification, ProtectionOperation } from '@/types';

function fault(partial: Partial<FaultClassification>): FaultClassification {
  return {
    id: 'f1',
    event_id: 'e1',
    fault_type: 'ABC',
    status: 'CLASSIFIED',
    is_primary: true,
    ...partial,
  } as FaultClassification;
}

function op(partial: Partial<ProtectionOperation>): ProtectionOperation {
  return {
    id: 'p1',
    event_id: 'e1',
    element: '87B',
    operation_type: 'TRIP',
    asserted: true,
    ...partial,
  } as ProtectionOperation;
}

describe('isDistanceApplicable', () => {
  it('hides km for differential without 21', () => {
    expect(
      isDistanceApplicable({
        fault: fault({
          distance_km: 1.7,
          features: { distance_applicable: false },
        }),
        protection: [op({ element: '87B' })],
      }),
    ).toBe(false);
  });

  it('does not treat BUS ZONE digital as distance', () => {
    expect(
      isDistanceApplicable({
        fault: fault({ distance_km: 1.7 }),
        protection: [
          op({ element: '87B', asserted: true }),
          op({ element: 'ZONE', asserted: true, operation_type: 'PICKUP' }),
        ],
      }),
    ).toBe(false);
  });

  it('allows distance when 21 operated', () => {
    expect(
      isDistanceApplicable({
        fault: fault({ features: { distance_applicable: true } }),
        protection: [op({ element: '21', asserted: true })],
      }),
    ).toBe(true);
  });

  it('allows 87 + 21 backup when backend flag is true', () => {
    expect(
      isDistanceApplicable({
        fault: fault({ features: { distance_applicable: true } }),
        protection: [
          op({ element: '87L', asserted: true }),
          op({ element: '21', asserted: false, operation_type: 'ASSESSMENT' }),
        ],
      }),
    ).toBe(true);
  });

  it('allows km when frontend sees 87L trip and 21 assessment enabled', () => {
    expect(
      isDistanceApplicable({
        fault: fault({ features: {} }),
        protection: [
          op({ element: '87L', asserted: true, operation_type: 'TRIP' }),
          op({ element: '21', asserted: false, operation_type: 'ASSESSMENT' }),
        ],
      }),
    ).toBe(true);
  });

  it('hides km for OC-only even if distance_km leaked', () => {
    expect(
      isDistanceApplicable({
        fault: fault({ distance_km: 3.2, features: {} }),
        protection: [op({ element: '51', asserted: true })],
      }),
    ).toBe(false);
  });
});
