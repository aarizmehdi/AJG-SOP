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
      if (url.endsWith('/original/preview'))
        return Promise.resolve(
          new Response(
            JSON.stringify({
              kind: 'pdf',
              url: 'https://example.test/private-pdf',
              file_name: 'Store SOP.pdf',
              media_type: 'application/pdf',
              legacy_repair_required: false,
              expires_in_seconds: 120,
            }),
            {
              status: 200,
              headers: { 'Content-Type': 'application/json' },
            },
          ),
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
            version: { id: 'version-one', status: 'extraction_review' },
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
                    {
                      id: 'nested-steps',
                      kind: 'ordered_list',
                      text: null,
                      source: locator,
                      table: null,
                      list_items: [
                        {
                          text: 'Check records',
                          level: 0,
                          marker: '1.',
                          source: locator,
                          children: [
                            {
                              text: 'Compare totals',
                              level: 1,
                              marker: '1.',
                              source: locator,
                              children: [],
                            },
                          ],
                        },
                      ],
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
    fireEvent.change(screen.getByRole('textbox', { name: 'Item 1.1' }), {
      target: { value: 'Compare corrected totals' },
    });
    expect(
      screen.queryByRole('button', { name: 'Submit review' }),
    ).not.toBeInTheDocument();

    fireEvent.change(screen.getByDisplayValue('1. Opening'), {
      target: { value: '1. Updated opening' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Save correction' }));
    expect(
      await screen.findByRole('heading', { name: '1. Updated opening' }),
    ).toBeVisible();
    expect(screen.getByText('Compare corrected totals')).toBeVisible();
    expect(
      screen.getByRole('button', { name: 'Submit review' }),
    ).toBeDisabled();

    fireEvent.click(
      screen.getByRole('button', { name: 'Edit canonical content' }),
    );
    fireEvent.click(screen.getByRole('button', { name: 'Cancel editing' }));
    expect(
      screen.queryByDisplayValue('1. Updated opening'),
    ).not.toBeInTheDocument();
  });
});
