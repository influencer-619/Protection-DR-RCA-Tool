import { describe, expect, it } from 'vitest';
import {
  faultedPhasesForRx,
  filterImpedanceRowsForFault,
  filterRxPointsForFault,
  isRxLocusApplicable,
  preferredLoopIdsForFault,
} from './rxLocus';

describe('rxLocus', () => {
  it('is not applicable when distance scheme is off', () => {
    expect(isRxLocusApplicable(false, 'AG')).toBe(false);
    expect(isRxLocusApplicable(true, 'UNKNOWN')).toBe(false);
  });

  it('maps fault types to faulted phases', () => {
    expect([...faultedPhasesForRx('AG')!]).toEqual(['A']);
    expect([...faultedPhasesForRx('BC')!].sort()).toEqual(['B', 'C']);
    expect([...faultedPhasesForRx('ABC')!].sort()).toEqual(['A', 'B', 'C']);
  });

  it('prefers delta loop ids for LL / LLG', () => {
    expect(preferredLoopIdsForFault('ABG')[0]).toBe('loop_AB');
    expect(preferredLoopIdsForFault('AB')).toEqual(['loop_AB', 'ZAB']);
  });

  it('filters ABG to ZAB only — not ZA/ZB', () => {
    const pts = [
      { id: 'phase_A', label: 'ZA', r: 1, x: 2, color: '#a' },
      { id: 'phase_B', label: 'ZB', r: 3, x: 4, color: '#b' },
      { id: 'loop_AB', label: 'ZAB', r: 5, x: 6, color: '#c' },
      { id: 'phase_C', label: 'ZC', r: 7, x: 8, color: '#d' },
    ];
    expect(filterRxPointsForFault(pts, 'ABG').map((p) => p.label)).toEqual(['ZAB']);
    expect(filterRxPointsForFault(pts, 'AB').map((p) => p.id)).toEqual(['loop_AB']);
  });

  it('filters AG to ZAG / ZA', () => {
    const pts = [
      { id: 'loop_AG', label: 'ZAG', r: 1, x: 2, color: '#a' },
      { id: 'phase_B', label: 'ZB', r: 3, x: 4, color: '#b' },
    ];
    expect(filterRxPointsForFault(pts, 'AG').map((p) => p.label)).toEqual(['ZAG']);
  });

  it('does not show ZA/ZB alone for ABG when loop missing', () => {
    const pts = [
      { id: 'phase_A', label: 'ZA', r: 1, x: 2, color: '#a' },
      { id: 'phase_B', label: 'ZB', r: 3, x: 4, color: '#b' },
    ];
    expect(filterRxPointsForFault(pts, 'ABG')).toEqual([]);
  });

  it('filters impedance table rows to faulted loop', () => {
    const rows = [
      { quantity: 'Z_A', phase: 'A' },
      { quantity: 'Z_AG', phase: 'AG' },
      { quantity: 'Z_B', phase: 'B' },
      { quantity: 'Z_AB', phase: 'AB' },
      { quantity: 'Z_BC', phase: 'BC' },
    ];
    expect(filterImpedanceRowsForFault(rows, 'AG').map((r) => r.quantity)).toEqual(['Z_AG']);
    expect(filterImpedanceRowsForFault(rows, 'ABG').map((r) => r.quantity)).toEqual(['Z_AB']);
    expect(filterImpedanceRowsForFault(rows, 'ABC').map((r) => r.quantity)).toEqual([
      'Z_AB',
      'Z_BC',
    ]);
  });
});
