import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, expect, it, vi } from 'vitest';
import { LanguageProvider } from '../language/LanguageProvider';
import { PolicyPurgeDangerZone } from './PolicyPurgeDangerZone';

const preview = {
  policy_id: 'p1',
  title: 'AJG Stock policy',
  published: true,
  counts: {
    mongo: {
      policy_versions: 3,
      source_documents: 2,
      raw_parser_results: 2,
      canonical_sops: 2,
      ingestion_jobs: 2,
      retrieval_chunks: 18,
    },
    r2_objects: 12,
    r2_bytes: 1024,
    pinecone_vectors: 28,
  },
  preview_token: 'snapshot',
  limitations: [],
};
afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});
function mount() {
  localStorage.setItem('ajt-fixture-identity', 'system-admin');
  return render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { mutations: { retry: false } } })
      }
    >
      <LanguageProvider>
        <MemoryRouter initialEntries={['/admin/policies/p1']}>
          <Routes>
            <Route
              path="/admin/policies/p1"
              element={<PolicyPurgeDangerZone policyId="p1" />}
            />
            <Route
              path="/admin/policies"
              element={<p>Library after deletion</p>}
            />
          </Routes>
        </MemoryRouter>
      </LanguageProvider>
    </QueryClientProvider>,
  );
}
it('previews first, requires both exact confirmations, and clears cached content on success', async () => {
  const fetch = vi.fn((url: string, init?: RequestInit) => {
    if (url.endsWith('purge-preview'))
      return Promise.resolve(new Response(JSON.stringify(preview)));
    if (typeof init?.body !== 'string')
      throw new Error('Expected JSON request body');
    expect(JSON.parse(init.body)).toEqual({
      title: preview.title,
      phrase: 'DELETE PERMANENTLY',
      preview_token: 'snapshot',
    });
    return Promise.resolve(
      new Response(
        JSON.stringify({
          policy_id: 'p1',
          status: 'complete',
          counts: preview.counts,
          stages: { mongo: 'complete' },
          remaining: {
            mongo_references: 0,
            r2_objects: 0,
            pinecone_vectors: 0,
          },
          error: null,
        }),
      ),
    );
  });
  vi.stubGlobal('fetch', fetch);
  mount();
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole('button', { name: 'Permanently delete policy' }),
  );
  expect(await screen.findByText('AJG Stock policy')).toBeVisible();
  expect(screen.getByText('Pinecone vectors')).toBeVisible();
  const confirm = screen.getByRole('button', { name: 'Delete permanently' });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Type the exact policy title'), {
    target: { value: 'wrong title' },
  });
  fireEvent.change(screen.getByLabelText('Type DELETE PERMANENTLY'), {
    target: { value: 'DELETE PERMANENTLY' },
  });
  expect(confirm).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Type the exact policy title'), {
    target: { value: preview.title },
  });
  expect(confirm).toBeEnabled();
  fireEvent.click(confirm);
  expect(await screen.findByText('Library after deletion')).toBeVisible();
  expect(fetch).toHaveBeenCalledTimes(2);
});
it('shows failed stages and retains confirmation for a safe retry', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn((url: string) =>
      Promise.resolve(
        new Response(
          JSON.stringify(
            url.endsWith('purge-preview')
              ? preview
              : {
                  policy_id: 'p1',
                  status: 'failed',
                  counts: preview.counts,
                  stages: { pinecone: 'complete', r2: 'failed' },
                  remaining: {},
                  error: 'retry',
                },
          ),
        ),
      ),
    ),
  );
  mount();
  fireEvent.click(
    screen.getByRole('button', { name: 'Permanently delete policy' }),
  );
  await screen.findByText('AJG Stock policy');
  fireEvent.change(screen.getByLabelText('Type the exact policy title'), {
    target: { value: preview.title },
  });
  fireEvent.change(screen.getByLabelText('Type DELETE PERMANENTLY'), {
    target: { value: 'DELETE PERMANENTLY' },
  });
  fireEvent.click(screen.getByRole('button', { name: 'Delete permanently' }));
  await waitFor(() => {
    expect(screen.getByRole('alert')).toHaveTextContent('r2: failed');
  });
  expect(
    screen.getByRole('button', { name: 'Delete permanently' }),
  ).toBeEnabled();
});
