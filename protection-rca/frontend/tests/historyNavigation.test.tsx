import { describe, expect, it } from 'vitest';
import { act } from 'react';
import { createMemoryRouter, RouterProvider } from 'react-router-dom';
import { render, screen, waitFor } from '@testing-library/react';

function PageA() {
  return <div>Page A</div>;
}
function PageB() {
  return <div>Page B</div>;
}

describe('browser-style history', () => {
  it('back and forward update the rendered route', async () => {
    const router = createMemoryRouter(
      [
        { path: '/a', element: <PageA /> },
        { path: '/b', element: <PageB /> },
      ],
      {
        initialEntries: ['/a'],
        initialIndex: 0,
        future: { v7_startTransition: true, v7_relativeSplatPath: true },
      },
    );

    render(<RouterProvider router={router} />);
    expect(screen.getByText('Page A')).toBeInTheDocument();

    await act(async () => {
      await router.navigate('/b');
    });
    await waitFor(() => expect(screen.getByText('Page B')).toBeInTheDocument());

    await act(async () => {
      await router.navigate(-1);
    });
    await waitFor(() => expect(screen.getByText('Page A')).toBeInTheDocument());

    await act(async () => {
      await router.navigate(1);
    });
    await waitFor(() => expect(screen.getByText('Page B')).toBeInTheDocument());
  });
});
