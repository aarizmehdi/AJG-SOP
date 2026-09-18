import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { LanguageContext } from '../language/language-context';
import { messages } from '../language/messages';
import AdminLibraryPage from './AdminLibraryPage';

function renderLibrary() {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <LanguageContext
        value={{
          language: 'english',
          hasPreference: true,
          profileId: 'admin',
          bindProfile: () => {},
          setLanguage: async () => {},
          t: (key) => messages.english[key],
        }}
      >
        <MemoryRouter initialEntries={['/admin/policies']}>
          <AdminLibraryPage />
        </MemoryRouter>
      </LanguageContext>
    </QueryClientProvider>,
  );
}

function profile(role: 'sop_admin' | 'system_admin') {
  return {
    id: `${role}-one`,
    organization_id: 'ajt',
    display_name:
      role === 'sop_admin' ? 'SOP Administrator' : 'System Administrator',
    email: `${role}@example.test`,
    application_roles: [role],
    departments: ['Operations'],
    locations: ['Peshawar'],
    organizational_roles: [],
    preferred_language: 'english',
  };
}

function stubLibrary(role: 'sop_admin' | 'system_admin') {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const body = url.endsWith('/profile/me') ? profile(role) : [];
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );
}

describe('policy library role actions', () => {
  it('does not expose ingestion actions to an SOP administrator', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'sop-admin');
    stubLibrary('sop_admin');
    renderLibrary();
    await screen.findByText('No SOPs have been added yet');
    expect(
      screen.queryByRole('link', { name: /Add SOP/i }),
    ).not.toBeInTheDocument();
  });

  it('keeps ingestion actions available to a system administrator', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'system-admin');
    stubLibrary('system_admin');
    renderLibrary();
    expect(
      await screen.findAllByRole('link', { name: /Add SOP/i }),
    ).not.toHaveLength(0);
  });
});
