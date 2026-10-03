import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import { LanguageContext } from '../language/language-context';
import { messages } from '../language/messages';
import AssistantPage from './AssistantPage';

function eventStream(events: [string, unknown][]) {
  return new Response(
    events
      .map(
        ([name, data]) => `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`,
      )
      .join(''),
    { status: 200, headers: { 'Content-Type': 'text/event-stream' } },
  );
}

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
  vi.unstubAllEnvs();
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
        eventStream([
          [
            'answer_start',
            {
              kind: 'policy_answer',
              answerable: true,
              language: 'english',
              verified: true,
            },
          ],
          ['answer_delta', { text: 'English answer must not appear' }],
          ['sources', { citations: [] }],
          ['done', { verified: true }],
        ]),
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

  it('lets the employee cancel a voice recording without submitting it', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    vi.stubEnv('VITE_VOICE_INPUT_ENABLED', 'true');
    const stopTrack = vi.fn();
    vi.stubGlobal('navigator', {
      mediaDevices: {
        getUserMedia: vi.fn().mockResolvedValue({
          getTracks: () => [{ stop: stopTrack }],
        }),
      },
    });
    class FakeMediaRecorder {
      state = 'inactive';
      mimeType = 'audio/webm';
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;

      start() {
        this.state = 'recording';
      }

      stop() {
        this.state = 'inactive';
        this.onstop?.();
      }
    }
    vi.stubGlobal('MediaRecorder', FakeMediaRecorder);
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    renderAssistant();
    fireEvent.click(
      screen.getByRole('button', { name: 'Awaz se sawal shuru karein' }),
    );
    await screen.findByText(/Sun rahe hain/);
    await waitFor(() => {
      fireEvent.keyDown(document, { key: 'Escape' });
      expect(stopTrack).toHaveBeenCalledOnce();
    });
    expect(fetchMock).not.toHaveBeenCalled();
    expect(screen.getByRole('textbox')).toHaveValue('');
  });

  it('links a verified citation to its canonical policy section', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    vi.stubGlobal('crypto', { randomUUID: () => 'turn-citation' });
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          eventStream([
            ['status', { stage: 'retrieving' }],
            [
              'answer_start',
              {
                kind: 'policy_answer',
                answerable: true,
                language: 'roman_urdu',
                verified: true,
              },
            ],
            ['answer_delta', { text: '**Gate register** mein entry karein.' }],
            [
              'sources',
              {
                citations: [
                  {
                    chunk_id: 'chunk-one',
                    policy_id: 'policy-one',
                    policy_title: 'Gate SOP',
                    section_id: 'entry-register',
                    heading_path: ['Gate', 'Entry register'],
                    document_id: 'document-one',
                    source: {
                      source_document_id: 'source-one',
                      page_start: 3,
                      page_end: 3,
                      sheet_name: null,
                      cell_range: null,
                      block_anchor: null,
                    },
                  },
                ],
              },
            ],
            ['done', { verified: true }],
          ]),
        ),
      ),
    );
    renderAssistant();
    const field = screen.getByRole('textbox');
    fireEvent.change(field, { target: { value: 'Gate entry kaise karein?' } });
    fireEvent.keyDown(field, { key: 'Enter' });

    expect(await screen.findByText('Gate SOP')).toBeVisible();
    expect(screen.getByRole('link', { name: /Gate SOP/ })).toHaveAttribute(
      'href',
      '/policies/policy-one?section=entry-register',
    );
  });

  it('renders safe Markdown and discards conversation after remount', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    vi.stubGlobal('crypto', { randomUUID: () => 'turn-markdown' });
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          eventStream([
            [
              'answer_start',
              {
                kind: 'policy_answer',
                answerable: true,
                language: 'roman_urdu',
                verified: true,
              },
            ],
            [
              'answer_delta',
              {
                text: '**Important**\n\n1. Pehla qadam\n2. Doosra qadam\n\n<script>alert(1)</script>\n\n[bad](javascript:alert(1))',
              },
            ],
            ['sources', { citations: [] }],
            ['done', { verified: true }],
          ]),
        ),
      ),
    );
    const mounted = renderAssistant();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'What is the procedure?' },
    });
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
    expect(await screen.findByText('Important')).toHaveProperty(
      'tagName',
      'STRONG',
    );
    expect(screen.getByText('Pehla qadam')).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
    expect(document.querySelector('.answer-markdown a')).toBeNull();
    mounted.unmount();
    renderAssistant();
    expect(
      screen.getByText('SOP ke bare mein kaise madad karun?'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('What is the procedure?'),
    ).not.toBeInTheDocument();
    expect(window.localStorage.getItem('ajt-fixture-identity')).toBe(
      'employee',
    );
    expect(window.localStorage.length).toBe(1);
  });

  it('aborts an in-flight request on leaving the Assistant page', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    vi.stubGlobal('crypto', { randomUUID: () => 'turn-abort' });
    let requestSignal: AbortSignal | undefined;
    vi.stubGlobal(
      'fetch',
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        requestSignal = init?.signal ?? undefined;
        return new Promise<Response>(() => {});
      }),
    );
    const mounted = renderAssistant();
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Explain the policy' },
    });
    fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
    await waitFor(() => {
      expect(requestSignal).toBeDefined();
    });
    mounted.unmount();
    expect(requestSignal?.aborted).toBe(true);
  });

  it('bounds twenty turns to eight prior user questions and resets on remount', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    vi.stubGlobal('crypto', { randomUUID: () => Math.random().toString(36) });
    const requests: { history: { role: string; content: string }[] }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn((_input: RequestInfo | URL, init?: RequestInit) => {
        requests.push(
          JSON.parse(init?.body as string) as {
            history: { role: string; content: string }[];
          },
        );
        return Promise.resolve(
          eventStream([
            [
              'answer_start',
              {
                kind: 'no_answer',
                answerable: false,
                language: 'roman_urdu',
                verified: true,
              },
            ],
            ['answer_delta', { text: 'SOP detail available nahin.' }],
            ['sources', { citations: [] }],
            ['done', { verified: true }],
          ]),
        );
      }),
    );
    const mounted = renderAssistant();
    const field = screen.getByRole('textbox');
    for (let index = 0; index < 20; index += 1) {
      fireEvent.change(field, {
        target: { value: `What about step ${String(index)}?` },
      });
      fireEvent.keyDown(field, { key: 'Enter' });
      await waitFor(() => {
        expect(screen.getAllByText('SOP detail available nahin.')).toHaveLength(
          index + 1,
        );
      });
    }
    expect(requests).toHaveLength(20);
    expect(requests[19]?.history).toHaveLength(8);
    expect(requests[19]?.history.every((turn) => turn.role === 'user')).toBe(
      true,
    );
    mounted.unmount();
    renderAssistant();
    expect(
      screen.getByText('SOP ke bare mein kaise madad karun?'),
    ).toBeInTheDocument();
    expect(screen.queryByText('What about step 19?')).not.toBeInTheDocument();
  });
});
