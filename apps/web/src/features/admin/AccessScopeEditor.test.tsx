import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { AccessScopeEditor } from './AccessScopeEditor';
import { CatalogMultiSelect } from '../system-admin/CatalogMultiSelect';

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('AccessScopeEditor', () => {
  it('uses authoritative catalog choices instead of arbitrary text', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'system-admin');
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url =
          typeof input === 'string'
            ? input
            : input instanceof URL
              ? input.href
              : input.url;
        const item = url.includes('departments')
          ? { id: 'department-store', key: 'store', name: 'Store' }
          : url.includes('locations')
            ? { id: 'location-mill', key: 'mill-1', name: 'Mill 1' }
            : { id: 'role-keeper', key: 'store_keeper', name: 'Store Keeper' };
        return Promise.resolve(
          new Response(
            JSON.stringify([
              {
                ...item,
                organization_id: 'ajt',
                description: null,
                active: true,
                version: 1,
                created_at: '2026-01-01T00:00:00Z',
                updated_at: '2026-01-01T00:00:00Z',
              },
            ]),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      }),
    );
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { queries: { retry: false } } })
        }
      >
        <AccessScopeEditor
          value={{
            departments: { mode: 'selected', values: ['store'] },
            locations: { mode: 'selected', values: ['mill-1'] },
            roles: { mode: 'selected', values: ['store_keeper'] },
          }}
          onChange={() => {}}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('Store Keeper')).toBeVisible();
    expect(screen.getByRole('checkbox', { name: 'Store' })).toBeChecked();
    expect(
      screen.queryByPlaceholderText('Comma-separated values'),
    ).not.toBeInTheDocument();
  });

  it('keeps a selected inactive historical key visible but blocks new assignment', () => {
    render(
      <CatalogMultiSelect
        label="Departments"
        items={[
          {
            id: 'department-old',
            organization_id: 'ajt',
            key: 'old-store',
            name: 'Old Store',
            description: null,
            active: false,
            version: 2,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-02-01T00:00:00Z',
          },
          {
            id: 'department-closed',
            organization_id: 'ajt',
            key: 'closed-store',
            name: 'Closed Store',
            description: null,
            active: false,
            version: 2,
            created_at: '2026-01-01T00:00:00Z',
            updated_at: '2026-02-01T00:00:00Z',
          },
        ]}
        value={['old-store']}
        onChange={() => {}}
      />,
    );

    expect(screen.getByRole('checkbox', { name: 'Old Store' })).toBeChecked();
    expect(screen.getByRole('checkbox', { name: 'Old Store' })).toBeEnabled();
    expect(
      screen.getByRole('checkbox', { name: 'Closed Store' }),
    ).toBeDisabled();
    expect(screen.getAllByText(/Inactive/)).toHaveLength(2);
  });
});
