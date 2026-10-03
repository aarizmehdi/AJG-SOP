import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../../../api/client';
import CreateUserPage from './CreateUserPage';

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

describe('create user with optional assignments', () => {
  it('explains empty catalogs and submits a department-only user', async () => {
    vi.mocked(apiRequest).mockResolvedValue({
      user: { id: 'created-user', display_name: 'Department Employee' },
      activation_link: 'https://example.test/setup',
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter>
          <CreateUserPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );
    expect(
      screen.getByText(
        'No locations are configured yet. You can save this user without one and assign it later.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        'No organizational roles are configured yet. You can save this user without one and assign it later.',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('group', { name: 'Locations (optional)' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('group', { name: 'Organizational roles (optional)' }),
    ).toBeInTheDocument();
    const submit = screen.getByRole('button', { name: 'Create user' });
    expect(submit).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Full name'), {
      target: { value: 'Department Employee' },
    });
    fireEvent.change(screen.getByLabelText('Email address'), {
      target: { value: 'employee@example.test' },
    });
    expect(submit).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', { name: 'Store' }));
    expect(submit).toBeEnabled();
    fireEvent.click(submit);
    await waitFor(() => {
      expect(apiRequest).toHaveBeenCalledOnce();
    });
    const call = vi.mocked(apiRequest).mock.calls[0];
    if (!call) throw new Error('Create request was not sent');
    const [path, , request] = call;
    expect(path).toBe('/admin/users');
    expect(request?.method).toBe('POST');
    const body = request?.body;
    if (typeof body !== 'string')
      throw new Error('Expected a JSON request body');
    expect(JSON.parse(body)).toMatchObject({
      display_name: 'Department Employee',
      departments: ['store'],
      locations: [],
      organizational_roles: [],
      application_roles: ['employee'],
    });
    expect(await screen.findByText('Account created')).toBeInTheDocument();
  });
});
