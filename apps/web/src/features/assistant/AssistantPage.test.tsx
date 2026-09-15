import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { LanguageContext } from '../language/language-context';
import { messages } from '../language/messages';
import AssistantPage from './AssistantPage';

function renderAssistant() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
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
          <AssistantPage />
        </MemoryRouter>
      </LanguageContext>
    </QueryClientProvider>,
  );
}

afterEach(() => {
  window.localStorage.clear();
  vi.unstubAllGlobals();
});

describe('assistant response language', () => {
  it('uses selected Roman Urdu for an English question and withholds a mismatched response', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    vi.stubGlobal('crypto', { randomUUID: () => 'turn-one' });
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
      expect(
        JSON.parse(typeof init?.body === 'string' ? init.body : '{}'),
      ).toMatchObject({
        question: 'How do I handle damaged stock?',
        language: 'roman_urdu',
      });
      return Promise.resolve(
        new Response(
          JSON.stringify({
            organization_id: 'ajt',
            answerable: true,
            answer: 'English answer must not appear',
            language: 'english',
            citations: [],
            verified: true,
            session_id: 'session-one',
          }),
          { status: 200 },
        ),
      );
    });
    vi.stubGlobal('fetch', fetchMock);
    renderAssistant();
    const field = screen.getByRole('textbox');
    fireEvent.change(field, {
      target: { value: 'How do I handle damaged stock?' },
    });
    fireEvent.keyDown(field, { key: 'Enter', shiftKey: true });
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.keyDown(field, { key: 'Enter', isComposing: true });
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.keyDown(field, { key: 'Enter' });
    await waitFor(() => {
      expect(screen.getByText('Koi jawab jari nahin hua')).toBeInTheDocument();
    });
    expect(
      screen.queryByText('English answer must not appear'),
    ).not.toBeInTheDocument();
  });
});
