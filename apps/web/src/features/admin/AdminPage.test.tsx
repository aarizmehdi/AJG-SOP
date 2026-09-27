import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LanguageContext } from '../language/language-context';
import { messages } from '../language/messages';
import AdminPage from './AdminPage';

function renderAdmin(role: 'employee' | 'sop_admin' | 'system_admin') {
  window.localStorage.setItem('ajt-fixture-identity', role.replace('_', '-'));
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            id: `user-${role}`,
            organization_id: 'ajt',
            display_name: role,
            email: `${role}@example.test`,
            application_roles:
              role === 'system_admin'
                ? ['employee', 'sop_admin', 'system_admin']
                : role === 'sop_admin'
                  ? ['employee', 'sop_admin']
                  : ['employee'],
            departments: ['store'],
            locations: ['mill-1'],
            organizational_roles: ['manager'],
            preferred_language: 'english',
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    ),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <LanguageContext
        value={{
          language: 'english',
          hasPreference: true,
          profileId: `user-${role}`,
          bindProfile: () => {},
          setLanguage: async () => {},
          t: (key) => messages.english[key],
        }}
      >
        <MemoryRouter initialEntries={['/admin']}>
          <AdminPage />
        </MemoryRouter>
      </LanguageContext>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('administration navigation boundaries', () => {
  it('shows organization controls only to a System Administrator', async () => {
    renderAdmin('system_admin');
    expect(await screen.findByText('People & access')).toBeVisible();
    expect(screen.getByRole('link', { name: 'Users' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Audit Log' })).toBeVisible();
  });

  it('keeps an SOP Administrator inside scoped knowledge workflows', async () => {
    renderAdmin('sop_admin');
    expect(await screen.findByText('Knowledge workspace')).toBeVisible();
    expect(
      screen.queryByRole('link', { name: 'Users' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Audit Log' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'SOP Library' })).toBeVisible();
  });

  it('shows no administration controls to an employee', async () => {
    renderAdmin('employee');
    expect(
      await screen.findByText('Administrative access required'),
    ).toBeVisible();
    expect(
      screen.queryByRole('link', { name: 'Users' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'SOP Library' }),
    ).not.toBeInTheDocument();
  });
});
