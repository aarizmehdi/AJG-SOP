import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LanguageContext } from '../language/language-context';
import { messages } from '../language/messages';
import PolicyPage from './PolicyPage';

const locator = {
  source_document_id: 'source-one',
  page_start: 4,
  page_end: 4,
  bounding_boxes: [],
  text_start: null,
  text_end: null,
  sheet_name: null,
  cell_range: null,
  block_anchor: null,
};

function renderPolicy(originalAllowed = true) {
  window.localStorage.setItem('ajt-fixture-identity', 'employee');
  vi.stubGlobal(
    'fetch',
    vi.fn(() =>
      Promise.resolve(
        new Response(
          JSON.stringify({
            policy_id: 'policy-one',
            title: 'Store Operations SOP',
            category: 'Operations',
            version_label: '2.0',
            original_download_allowed: originalAllowed,
            original_sources: originalAllowed
              ? [
                  {
                    source_id: 'source-one',
                    file_name: 'Store Operations.pdf',
                    media_type: 'application/pdf',
                    source_format: 'pdf',
                  },
                ]
              : [],
            sections: [
              {
                organization_id: 'ajt',
                policy_id: 'policy-one',
                version_id: 'version-one',
                section_id: 'opening',
                heading: '1. Opening procedure',
                heading_path: ['Store operations', 'Opening procedure'],
                heading_level: 1,
                parent_section_id: null,
                chapter: 'Chapter 1',
                policy_number: 'OPS-01',
                content: '**raw markdown fallback must not render**',
                source: locator,
                blocks: [
                  {
                    id: 'steps',
                    kind: 'ordered_list',
                    text: null,
                    source: locator,
                    list_items: [
                      {
                        text: 'Unlock the main entrance',
                        level: 0,
                        marker: '1.',
                        children: [
                          {
                            text: 'Record the opening time',
                            level: 1,
                            marker: 'a.',
                            children: [],
                            source: locator,
                          },
                        ],
                        source: locator,
                      },
                    ],
                    table: null,
                  },
                  {
                    id: 'register',
                    kind: 'table',
                    text: null,
                    source: locator,
                    list_items: [],
                    table: {
                      caption: 'Opening register',
                      cells: [
                        {
                          row: 0,
                          column: 0,
                          text: 'Task',
                          row_span: 1,
                          column_span: 1,
                          is_header: true,
                          source: locator,
                        },
                        {
                          row: 1,
                          column: 0,
                          text: 'Cash count',
                          row_span: 1,
                          column_span: 1,
                          is_header: false,
                          source: locator,
                        },
                      ],
                    },
                  },
                ],
              },
            ],
          }),
          { status: 200, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    ),
  );
  render(
    <QueryClientProvider client={new QueryClient()}>
      <LanguageContext
        value={{
          language: 'english',
          hasPreference: true,
          profileId: 'employee-one',
          bindProfile: () => {},
          setLanguage: async () => {},
          t: (key) => messages.english[key],
        }}
      >
        <MemoryRouter initialEntries={['/policies/policy-one?section=opening']}>
          <Routes>
            <Route path="/policies/:policyId" element={<PolicyPage />} />
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

describe('employee canonical policy reader', () => {
  it('renders canonical hierarchy, nested lists, tables, and an authorized original action', async () => {
    renderPolicy();

    expect(
      await screen.findByRole('heading', { name: '1. Opening procedure' }),
    ).toBeVisible();
    expect(screen.getByText('Record the opening time')).toBeVisible();
    expect(screen.getByRole('table')).toHaveTextContent('Cash count');
    expect(screen.queryByText(/raw markdown fallback/)).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'View Original PDF' }),
    ).toBeVisible();
    expect(screen.getByLabelText('1. Opening procedure')).toHaveClass(
      'canonical-section--focused',
    );
  });

  it('does not expose an original action when the backend withholds it', async () => {
    renderPolicy(false);

    expect(
      await screen.findByRole('heading', { name: '1. Opening procedure' }),
    ).toBeVisible();
    expect(
      screen.queryByRole('button', { name: 'View Original PDF' }),
    ).not.toBeInTheDocument();
  });
});
