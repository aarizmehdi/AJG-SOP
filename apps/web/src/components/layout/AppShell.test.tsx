import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
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

  it('shows the full context-aware workspace for system administrators', async () => {
    renderShell(
      {
        ...baseProfile,
        application_roles: ['employee', 'sop_admin', 'system_admin'],
      },
      '/admin/users',
    );

    const users = await screen.findByRole('link', { name: 'Users' });
    expect(users).toHaveAttribute('href', '/admin/users');
    expect(users).toHaveClass('active');
    expect(
      screen.queryByRole('link', { name: 'Home' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'Search SOPs' }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'People & Access' }),
    ).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(screen.getByRole('button', { name: 'Knowledge' }));
    expect(screen.getByRole('link', { name: 'SOP Library' })).toBeVisible();
    expect(screen.getByRole('link', { name: 'Add SOP' })).toBeVisible();

    fireEvent.click(screen.getByRole('button', { name: 'Governance' }));
    expect(screen.getByRole('link', { name: 'Audit Log' })).toBeVisible();
  });

  it('keeps the Policy Library entry for scoped SOP administrators', async () => {
    renderShell(
      { ...baseProfile, application_roles: ['employee', 'sop_admin'] },
      '/admin/policies',
    );

    const link = await screen.findByRole('link', { name: 'SOP Library' });
    expect(link).toHaveAttribute('href', '/admin/policies');
    expect(link).toHaveClass('active');
    expect(
      screen.queryByRole('link', { name: 'System Admin' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Review Queue' })).toBeVisible();
    expect(
      screen.queryByRole('link', { name: 'Add SOP' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('button', { name: 'People & Access' }),
    ).not.toBeInTheDocument();
  });

  it('does not expose an administration entry to employees', async () => {
    renderShell(baseProfile, '/home');

    expect(await screen.findByRole('link', { name: 'Home' })).toBeVisible();
    expect(
      screen.queryByRole('link', { name: 'System Admin' }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole('link', { name: 'SOP Library' }),
    ).not.toBeInTheDocument();
  });

  it('opens and closes the administration drawer from the mobile-header control', async () => {
    renderShell(
      {
        ...baseProfile,
        application_roles: ['employee', 'sop_admin', 'system_admin'],
      },
      '/admin/overview',
    );

    const open = await screen.findByRole('button', {
      name: 'Open administration navigation',
    });
    fireEvent.click(open);
    const closeControls = screen.getAllByRole('button', {
      name: 'Close administration navigation',
    });
    const close = closeControls.find(
      (control) => control.getAttribute('aria-expanded') === 'true',
    );
    expect(close).toHaveAttribute('aria-expanded', 'true');
    expect(close).toBeDefined();
    if (!close) throw new Error('Close navigation control was not rendered');
    fireEvent.click(close);
    expect(
      screen.getByRole('button', { name: 'Open administration navigation' }),
    ).toHaveAttribute('aria-expanded', 'false');
  });
});
