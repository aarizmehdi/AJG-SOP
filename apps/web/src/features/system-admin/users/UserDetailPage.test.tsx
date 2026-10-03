import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { apiRequest } from '../../../api/client';
import UserDetailPage from './UserDetailPage';

vi.mock('../../../api/client', () => ({ apiRequest: vi.fn() }));
vi.mock('../catalogs', () => ({
  useOrganizationCatalogs: () => ({
    isPending: false,
    isError: false,
    data: {
      departments: [{ id: 'store', key: 'store', name: 'Store', active: true }],
      locations: [],
      organizational_roles: [],
    },
  }),
}));

describe('legacy user edit', () => {
  it('submits only visible current catalog assignments', async () => {
    const user = {
      id: 'legacy-user',
      display_name: 'Legacy employee',
      email: 'legacy@example.test',
      identity_linked: true,
      status: 'active',
      active: true,
      version: 1,
      preferred_language: 'english',
      application_roles: ['employee'],
      departments: ['operations'],
      locations: ['head-office'],
      organizational_roles: ['employee'],
      management_departments: [],
      management_locations: [],
      management_roles: [],
    };
    vi.mocked(apiRequest).mockImplementation((path, _schema, init) => {
      if (init?.method === 'PATCH') {
        return Promise.resolve({ ...user, version: 2 });
      }
      if (path === '/profile/me')
        return Promise.resolve({ id: 'system-admin' });
      if (path.startsWith('/admin/audit-events'))
        return Promise.resolve({ items: [] });
      return Promise.resolve(user);
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={['/admin/users/legacy-user']}>
          <Routes>
            <Route path="/admin/users/:userId" element={<UserDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      await screen.findByText(/legacy access assignments/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Store' }));
    fireEvent.click(
      screen.getByRole('button', { name: 'Save access changes' }),
    );
    await waitFor(() => {
      expect(
        vi
          .mocked(apiRequest)
          .mock.calls.some(([, , init]) => init?.method === 'PATCH'),
      ).toBe(true);
    });
    const request = vi
      .mocked(apiRequest)
      .mock.calls.find(([, , init]) => init?.method === 'PATCH');
    const body = request?.[2]?.body;
    if (typeof body !== 'string') throw new Error('Expected JSON request body');
    const payload = z
      .object({
        departments: z.array(z.string()),
        locations: z.array(z.string()),
        organizational_roles: z.array(z.string()),
      })
      .parse(JSON.parse(body) as unknown);
    expect(payload.departments).toEqual(['store']);
    expect(payload.locations).toEqual([]);
    expect(payload.organizational_roles).toEqual([]);
  });
});
