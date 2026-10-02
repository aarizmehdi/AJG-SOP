import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LanguageContext } from '../language/language-context';
import { messages } from '../language/messages';
import ExtractionReviewPage from './ExtractionReviewPage';

const locator = {
  source_document_id: 'source-one',
  page_start: 1,
  page_end: 1,
  bounding_boxes: [],
  text_start: null,
  text_end: null,
  sheet_name: null,
  cell_range: null,
  block_anchor: null,
};

function renderReview() {
  window.localStorage.setItem('ajt-fixture-identity', 'system-admin');
  const NativeURL = URL;
  class PreviewURL extends NativeURL {
    static createObjectURL = vi.fn(() => 'blob:preview');
    static revokeObjectURL = vi.fn();
  }
  vi.stubGlobal('URL', PreviewURL);
  vi.stubGlobal(
    'fetch',
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url =
        typeof input === 'string'
          ? input
          : input instanceof Request
            ? input.url
            : input.href;
      if (url.endsWith('/profile/me'))
        return Promise.resolve(
          new Response(
            JSON.stringify({
              id: 'admin-one',
              organization_id: 'ajt',
              display_name: 'System Admin',
              email: 'admin@example.test',
              application_roles: ['employee', 'sop_admin', 'system_admin'],
              departments: [],
              locations: [],
              organizational_roles: [],
              preferred_language: 'english',
            }),
            { status: 200, headers: { 'Content-Type': 'application/json' } },
          ),
        );
      if (url.endsWith('/original'))
        return Promise.resolve(
          new Response(new Blob(['pdf']), {
            status: 200,
            headers: { 'Content-Type': 'application/pdf' },
          }),
        );
      if (init?.method === 'PUT')
        return Promise.resolve(
          new Response(
            JSON.stringify(
              typeof init.body === 'string'
                ? (JSON.parse(init.body) as { canonical: unknown }).canonical
                : {},
            ),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
          ),
        );
      return Promise.resolve(
        new Response(
          JSON.stringify({
            source: {
              id: 'source-one',
              organization_id: 'ajt',
              policy_id: 'policy-one',
              version_id: 'version-one',
              file_name: 'Store SOP.pdf',
              media_type: 'application/pdf',
              source_format: 'pdf',
              sha256: 'hash',
              original_artifact_uri: 'private/source.pdf',
              status: 'review_required',
              parser_provider: 'fixture',
              parser_version: '1',
              raw_artifact_uri: 'private/raw.json',
              canonical_artifact_uri: 'private/canonical.json',
              reviewed_artifact_uri: null,
              error_code: null,
              created_at: '2026-10-02T00:00:00Z',
            },
            raw: { title: 'Store SOP', blocks: [], warnings: [] },
            canonical: {
              id: 'canonical-one',
              organization_id: 'ajt',
              policy_id: 'policy-one',
              version_id: 'version-one',
              title: 'Store SOP',
              approved: false,
              sections: [
                {
                  id: 'opening',
                  stable_key: 'opening',
                  heading: '1. Opening',
                  heading_level: 1,
                  heading_path: ['Opening'],
                  policy_number: 'OPS-01',
                  source: locator,
                  blocks: [
                    {
                      id: 'opening-text',
                      kind: 'paragraph',
                      text: 'Open the store with two employees present.',
                      list_items: [],
                      table: null,
                      source: locator,
                    },
                  ],
                },
              ],
            },
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      );
    }),
  );

  render(
    <QueryClientProvider client={new QueryClient()}>
      <LanguageContext
        value={{
          language: 'english',
          hasPreference: true,
          profileId: 'admin-one',
          bindProfile: () => {},
          setLanguage: async () => {},
          t: (key) => messages.english[key],
        }}
      >
        <MemoryRouter initialEntries={['/admin/review/source-one']}>
          <Routes>
            <Route
              path="/admin/review/:sourceId"
              element={<ExtractionReviewPage />}
            />
          </Routes>
        </MemoryRouter>
      </LanguageContext>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe('extraction review workspace', () => {
  it('starts with a read-only canonical comparison and enters editing explicitly', async () => {
    renderReview();

    expect(
      await screen.findByRole('heading', { name: '1. Opening' }),
    ).toBeVisible();
    expect(screen.getByText('Read-only preview')).toBeVisible();
    expect(screen.queryByDisplayValue('1. Opening')).not.toBeInTheDocument();

    fireEvent.click(
      screen.getByRole('button', { name: 'Edit canonical content' }),
    );
    expect(screen.getByDisplayValue('1. Opening')).toBeVisible();
    expect(
      screen.getByRole('button', { name: 'Submit review' }),
    ).toBeDisabled();

    fireEvent.change(screen.getByDisplayValue('1. Opening'), {
      target: { value: '1. Updated opening' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save correction' }));
    expect(
      await screen.findByRole('heading', { name: '1. Updated opening' }),
    ).toBeVisible();

    fireEvent.click(
      screen.getByRole('button', { name: 'Edit canonical content' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel editing' }));
    expect(
      screen.queryByDisplayValue('1. Updated opening'),
    ).not.toBeInTheDocument();
  });
});
