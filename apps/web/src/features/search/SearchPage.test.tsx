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
});
