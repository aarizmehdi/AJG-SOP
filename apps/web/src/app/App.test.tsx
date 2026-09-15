import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { AppShell } from '../components/layout/AppShell';
import { LanguageProvider } from '../features/language/LanguageProvider';

describe('AppShell', () => {
  it('exposes familiar navigation labels', () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <LanguageProvider>
          <MemoryRouter>
            <AppShell />
          </MemoryRouter>
        </LanguageProvider>
      </QueryClientProvider>,
    );
    expect(
      screen.getByRole('navigation', { name: 'SOP Knowledge' }),
    ).toBeTruthy();
    expect(screen.getByText('Search SOPs')).toBeTruthy();
    expect(screen.getByText('SOP Assistant')).toBeTruthy();
  });
});
