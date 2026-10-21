import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LanguageContext } from '../language/language-context';
import { messages } from '../language/messages';
import AdminLibraryPage from './AdminLibraryPage';

function renderLibrary(
  route = '/admin/policies',
  language: 'english' | 'urdu' = 'english',
) {
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <LanguageContext
        value={{
          language,
          hasPreference: true,
          profileId: 'admin',
          bindProfile: () => {},
          setLanguage: async () => {},
          t: (key) => messages[language][key],
        }}
      >
        <MemoryRouter initialEntries={[route]}>
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

function stubLibrary(
  role: 'sop_admin' | 'system_admin',
  policyBody: unknown[] = [],
) {
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof URL
            ? input.href
            : input.url;
      const body = url.endsWith('/profile/me') ? profile(role) : policyBody;
      return Promise.resolve(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }),
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

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

  it('hides archived policies by default and exposes them through the status filter', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'system-admin');
    stubLibrary('system_admin', [
      {
        id: 'archived-policy',
        organization_id: 'ajt',
        title: 'Archived returns policy',
        category: 'Operations',
        policy_number: 'SOP-76',
        status: 'inactive',
        active_version_id: 'version-1',
        created_at: '2026-09-01T00:00:00Z',
        updated_at: '2026-09-20T00:00:00Z',
        display_version_id: 'version-1',
        versions: [
          {
            id: 'version-1',
            organization_id: 'ajt',
            policy_id: 'archived-policy',
            version_label: '1.0',
            status: 'published',
            access: {
              departments: { mode: 'all', values: [] },
              locations: { mode: 'all', values: [] },
              roles: { mode: 'all', values: [] },
            },
            source_document_ids: [],
            canonical_document_ids: [],
            index_revision: 'revision-1',
            created_at: '2026-09-01T00:00:00Z',
            published_at: '2026-09-02T00:00:00Z',
            effective_date: null,
          },
        ],
        sources: [],
        section_count: 1,
        page_count: 1,
      },
    ]);
    renderLibrary();

    await screen.findByText('0 documents');
    expect(
      screen.queryByText('Archived returns policy'),
    ).not.toBeInTheDocument();
    const statusFilter = screen.getAllByRole('combobox').at(0);
    if (!statusFilter) throw new Error('Status filter is missing');
    fireEvent.change(statusFilter, {
      target: { value: 'Inactive / Archived' },
    });

    const policyTitle = await screen.findByText('Archived returns policy');
    expect(policyTitle).toBeVisible();
    const policyCard = policyTitle.closest('article');
    if (!policyCard) throw new Error('Policy card is missing');
    expect(within(policyCard).getByText('Archived')).toBeVisible();
  });
});

it('clears review filters back to the review queue, not all current policies', async () => {
  window.localStorage.setItem('ajt-fixture-identity', 'system-admin');
  stubLibrary('system_admin');
  renderLibrary('/admin/review-queue');
  const status = (await screen.findAllByRole('combobox')).at(0);
  if (!status) throw new Error('Status filter missing');
  expect(status).toHaveValue('Review Required');
  fireEvent.change(screen.getByRole('searchbox'), {
    target: { value: 'missing' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
  expect(status).toHaveValue('Review Required');
  expect(screen.getByRole('searchbox')).toHaveValue('');
});

it('localizes icon-only filter controls and resets sort independently', async () => {
  window.localStorage.setItem('ajt-fixture-identity', 'system-admin');
  stubLibrary('system_admin');
  renderLibrary('/admin/policies', 'urdu');
  const selects = await screen.findAllByRole('combobox');
  const sort = selects.at(3);
  if (!sort) throw new Error('Sort filter missing');
  fireEvent.change(sort, { target: { value: 'Title A–Z' } });
  fireEvent.click(screen.getByRole('button', { name: 'ترتیب ری سیٹ کریں' }));
  expect(sort).toHaveValue('Recently Updated');
  fireEvent.change(screen.getByRole('searchbox'), {
    target: { value: 'policy' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'تلاش صاف کریں' }));
  expect(screen.getByRole('searchbox')).toHaveValue('');
});

it('keeps the review queue default when clearing the empty-results action', async () => {
  window.localStorage.setItem('ajt-fixture-identity', 'system-admin');
  stubLibrary('system_admin', [
    {
      id: 'published-synthetic',
      policy_number: null,
      organization_id: 'ajt',
      title: 'Synthetic published SOP',
      category: 'Operations',
      status: 'active',
      active_version_id: 'v1',
      created_at: '2026-09-01T00:00:00Z',
      updated_at: '2026-09-20T00:00:00Z',
      versions: [],
      sources: [],
      section_count: 1,
    },
  ]);
  renderLibrary('/admin/review-queue');
  await screen.findByText('No matching SOPs');
  fireEvent.click(screen.getByRole('button', { name: 'Clear filters' }));
  const status = screen.getAllByRole('combobox').at(0);
  if (!status) throw new Error('Status filter missing');
  expect(status).toHaveValue('Review Required');
  expect(screen.queryByText('Synthetic published SOP')).not.toBeInTheDocument();
});
