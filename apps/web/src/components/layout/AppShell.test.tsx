import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '../../api/client';
import { LanguageContext } from '../../features/language/language-context';
import { messages } from '../../features/language/messages';
import type { Profile } from '../../types/profile';
import { AppShell } from './AppShell';

vi.mock('../../api/client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../api/client')>();
  return { ...actual, apiRequest: vi.fn() };
});

const baseProfile: Profile = {
  id: 'admin-one',
  organization_id: 'ajt',
  display_name: 'Admin User',
  email: 'admin@example.test',
  application_roles: ['employee'],
  departments: ['store'],
  locations: ['head-office'],
  organizational_roles: ['manager'],
  management_departments: [],
  management_locations: [],
  management_roles: [],
  preferred_language: 'english',
  active: true,
  status: 'active',
  version: 1,
};

function renderShell(profile: Profile, path: string) {
  vi.mocked(apiRequest).mockResolvedValue(profile);
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  queryClient.setQueryData(['profile'], profile);
  render(
    <QueryClientProvider client={queryClient}>
      <LanguageContext
        value={{
          language: 'english',
          hasPreference: true,
          profileId: profile.id,
          bindProfile: () => {},
          setLanguage: async () => {},
          t: (key) => messages.english[key],
        }}
      >
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="*" element={<AppShell />} />
          </Routes>
        </MemoryRouter>
      </LanguageContext>
    </QueryClientProvider>,
  );
}

describe('AppShell role-aware admin navigation', () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockReset();
  });

  it('represents the control plane as System Admin for system administrators', async () => {
    renderShell(
      {
        ...baseProfile,
        application_roles: ['employee', 'sop_admin', 'system_admin'],
      },
      '/admin/users',
    );

    const link = await screen.findByRole('link', { name: 'System Admin' });
    expect(link).toHaveAttribute('href', '/admin/overview');
    expect(link).toHaveClass('active');
    expect(
      screen.queryByRole('link', { name: 'Policy Library' }),
    ).not.toBeInTheDocument();
  });

  it('keeps the Policy Library entry for scoped SOP administrators', async () => {
    renderShell(
      { ...baseProfile, application_roles: ['employee', 'sop_admin'] },
      '/admin/policies',
    );

    const link = await screen.findByRole('link', { name: 'Policy Library' });
    expect(link).toHaveAttribute('href', '/admin/policies');
    expect(link).toHaveClass('active');
    expect(
      screen.queryByRole('link', { name: 'System Admin' }),
    ).not.toBeInTheDocument();
  });

  it('does not expose an administration entry to employees', async () => {
    renderShell(baseProfile, '/home');

    expect(await screen.findByRole('link', { name: 'Home' })).toBeVisible();
    expect(
      screen.queryByRole('link', { name: 'System Admin' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Policy Library' }),
    ).not.toBeInTheDocument();
  });
});
