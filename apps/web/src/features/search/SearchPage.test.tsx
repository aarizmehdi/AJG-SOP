import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { LanguageContext } from '../language/language-context';
import { messages } from '../language/messages';
import SearchPage from './SearchPage';

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe('search language contract', () => {
  it('sends an Urdu query unchanged when the product locale is Roman Urdu', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    let sentBody = '';
    vi.stubGlobal(
      'fetch',
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        sentBody = typeof init?.body === 'string' ? init.body : '';
        return Promise.resolve(
          new Response(
            JSON.stringify({
              results: [],
              query: 'خراب سامان',
              language: 'roman_urdu',
            }),
            { status: 200 },
          ),
        );
      }),
    );
    render(
      <QueryClientProvider
        client={
          new QueryClient({ defaultOptions: { mutations: { retry: false } } })
        }
      >
        <LanguageContext
          value={{
            language: 'roman_urdu',
            hasPreference: true,
            profileId: 'employee-one',
            bindProfile: () => {},
            setLanguage: async () => {},
            t: (key) => messages.roman_urdu[key],
          }}
        >
          <MemoryRouter>
            <SearchPage />
          </MemoryRouter>
        </LanguageContext>
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'خراب سامان' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Talash karein' }));
    await waitFor(() => {
      expect(sentBody).not.toBe('');
    });
    expect(JSON.parse(sentBody)).toMatchObject({
      query: 'خراب سامان',
      language: 'roman_urdu',
    });
  });

  it('highlights matching query terms without injecting HTML', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              results: [
                {
                  organization_id: 'ajt',
                  chunk_id: 'chunk-one',
                  policy_id: 'policy-one',
                  version_id: 'version-one',
                  section_id: 'leave',
                  policy_title: 'Leave policy',
                  heading_path: ['Leave', 'Annual leave'],
                  policy_number: 'HR-1',
                  excerpt: 'Annual leave requires approval <img src=x>.',
                  source: {
                    source_document_id: 'source-one',
                    page_start: 2,
                    page_end: 2,
                    sheet_name: null,
                    cell_range: null,
                    block_anchor: null,
                  },
                  fused_score: 0.9,
                },
              ],
              query: 'annual approval',
              language: 'english',
            }),
            { status: 200 },
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
          <MemoryRouter>
            <SearchPage />
          </MemoryRouter>
        </LanguageContext>
      </QueryClientProvider>,
    );
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'annual approval' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Search' }));
    const marks = await screen.findAllByText(/annual|approval/i, {
      selector: 'mark',
    });
    expect(marks).toHaveLength(2);
    expect(document.querySelector('img')).toBeNull();
    expect(screen.getByText(/<img src=x>/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /View policy/ })).toHaveAttribute(
      'href',
      '/policies/policy-one?section=leave',
    );
  });
});
