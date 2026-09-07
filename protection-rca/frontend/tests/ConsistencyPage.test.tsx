import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { ConsistencyPage } from '@/pages/ConsistencyPage';
import { DEMO_FINDINGS, DEMO_SETTING_SOURCE } from '@/services/mockData';

vi.mock('@/services/api', () => ({
  api: {
    getConsistency: vi.fn(async () => ({
      findings: DEMO_FINDINGS,
      setting_source: DEMO_SETTING_SOURCE,
      overall_status: 'CONSISTENT_WITH_WARNINGS',
    })),
  },
}));

describe('ConsistencyPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders setting source banner and findings table', async () => {
    render(
      <MemoryRouter initialEntries={['/events/ev-001/consistency']}>
        <Routes>
          <Route path="/events/:id/consistency" element={<ConsistencyPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText(/consistency checker/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(/setting source/i)).toBeInTheDocument();
    });

    expect(screen.getByText(/ACTIVE_SETTING/i)).toBeInTheDocument();
    expect(screen.getByTestId('consistency-table')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId('finding-FND-001')).toBeInTheDocument();
    });

    expect(screen.getByText(/ZONE REACH/i)).toBeInTheDocument();
    expect(screen.getAllByText(/CONSISTENT|UNVERIFIABLE/).length).toBeGreaterThan(0);
  });
});
