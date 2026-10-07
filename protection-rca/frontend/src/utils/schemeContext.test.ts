import { describe, expect, it } from 'vitest';
import {
  bayFaultTypeFromAnalysis,
  baySchemeHintFromProtection,
  isDistanceApplicable,
  resolveBaySchemeHint,
  resolveDistanceApplicable,
  resolveFaultType,
  schemeHintFromReportAnalysis,
} from '@/utils/schemeContext';
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
  const base = {
    id: 'p1',
    event_id: 'e1',
    element: '87B',
    operation_type: 'TRIP',
    asserted: true,
    details: { evidence_ids: ['CH1'] },
    ...partial,
  };
  // Keep caller details but ensure evidence when asserted trip/pickup
  if (base.asserted && !(base.details as { evidence_ids?: unknown[] } | undefined)?.evidence_ids) {
    base.details = { ...(base.details as object), evidence_ids: ['CH1'] };
  }
  return base as ProtectionOperation;
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

describe('bay one-line analysis sync', () => {
  it('prefers live fault classification over event.fault_type', () => {
    expect(bayFaultTypeFromAnalysis(fault({ fault_type: 'ABC' }), 'UNKNOWN')).toBe('ABC');
    expect(bayFaultTypeFromAnalysis(null, 'AG')).toBe('AG');
  });

  it('builds scheme hint with pickup/trip like Protect table', () => {
    expect(
      baySchemeHintFromProtection([
        op({ element: '87T', operation_type: 'PICKUP', asserted: true }),
        op({ element: '87G', operation_type: 'PICKUP', asserted: true }),
      ]),
    ).toBe('87T PICKUP 87G PICKUP');
  });

  it('reads scheme hint from protection_assessment not wrong nested key', () => {
    expect(
      schemeHintFromReportAnalysis({
        protection: { assessments: [] },
        protection_assessment: [
          { element: '87T', pickup: true, trip: false },
        ],
      }),
    ).toBe('87T PICKUP');
  });

  it('resolveBaySchemeHint prefers live protection over report_analysis', () => {
    expect(
      resolveBaySchemeHint({
        protection: [op({ element: '87T', operation_type: 'PICKUP', asserted: true })],
        reportAnalysis: {
          protection_assessment: [{ element: '51', pickup: true, trip: true }],
        },
      }),
    ).toBe('87T PICKUP');
  });

  it('resolveFaultType prefers live fault then report_analysis then event', () => {
    expect(
      resolveFaultType({
        fault: fault({ fault_type: 'AB' }),
        eventFaultType: 'AG',
        reportAnalysis: { fault_classification: { fault_type: 'BC' } },
      }),
    ).toBe('AB');
    expect(
      resolveFaultType({
        fault: null,
        eventFaultType: 'AG',
        reportAnalysis: { fault_classification: { fault_type: 'UNKNOWN' } },
      }),
    ).toBe('UNKNOWN');
    expect(
      resolveFaultType({
        fault: null,
        eventFaultType: 'AG',
        reportAnalysis: {},
      }),
    ).toBe('AG');
  });

  it('resolveDistanceApplicable uses report_analysis flag consistently', () => {
    expect(
      resolveDistanceApplicable({
        fault: fault({ features: {} }),
        protection: [op({ element: '51' })],
        reportAnalysis: {
          fault_classification: {
            evidence: { distance_applicable: false },
            distance: { status: 'NOT_APPLICABLE' },
          },
        },
      }),
    ).toBe(false);
    expect(
      resolveDistanceApplicable({
        fault: fault({ features: {} }),
        protection: [op({ element: '21', asserted: true })],
        reportAnalysis: {
          fault_classification: {
            evidence: { distance_applicable: true },
            distance: { status: 'OK', value_km: 1.2 },
          },
        },
      }),
    ).toBe(true);
  });
});
