import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { LanguageContext } from '../language/language-context';
import { messages } from '../language/messages';
import { AvailablePolicies } from './AvailablePolicies';

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

function renderPolicies() {
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
          profileId: 'employee',
          bindProfile: () => {},
          setLanguage: async () => {},
          t: (key) => messages.english[key],
        }}
      >
        <MemoryRouter>
          <AvailablePolicies />
        </MemoryRouter>
      </LanguageContext>
    </QueryClientProvider>,
  );
}

describe('available policies', () => {
  it('renders backend-authorized policy summaries as reader links', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify([
              {
                policy_id: 'policy-76',
                title: 'Store returns procedure',
                policy_number: 'SOP-76',
                category: 'Operations',
                version_label: '1.0',
                effective_date: '2026-09-20',
                updated_at: '2026-09-20T00:00:00Z',
                recently_updated: true,
              },
            ]),
            { status: 200 },
          ),
        ),
      ),
    );

    renderPolicies();

    const link = await screen.findByRole('link', {
      name: /Store returns procedure/,
    });
    expect(link).toHaveAttribute('href', '/policies/policy-76');
    expect(screen.getByText(/SOP-76/)).toBeVisible();
    expect(screen.getByText(/Recently updated/)).toBeVisible();
  });
});
