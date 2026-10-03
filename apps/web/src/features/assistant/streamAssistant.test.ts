import { afterEach, describe, expect, it, vi } from 'vitest';
import { streamAssistant } from './streamAssistant';

function event(name: string, data: unknown) {
  return `event: ${name}\ndata: ${JSON.stringify(data)}\n\n`;
}

afterEach(() => {
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

describe('verified assistant stream', () => {
  it('parses split UTF-8 events and sends bounded ephemeral context with auth', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    const stream = [
      event('status', { stage: 'retrieving' }),
      event('answer_start', {
        kind: 'policy_answer',
        answerable: true,
        language: 'urdu',
        verified: true,
      }),
      event('answer_delta', { text: '**جواب**' }),
      event('sources', { citations: [] }),
      event('done', { verified: true }),
    ].join('');
    const bytes = new TextEncoder().encode(stream);
    const fetchMock = vi.fn((_url: string, init: RequestInit) => {
      expect(new Headers(init.headers).get('Authorization')).toBe(
        'Fixture employee',
      );
      expect(JSON.parse(init.body as string)).toMatchObject({
        language: 'urdu',
        history: [],
      });
      return Promise.resolve(
        new Response(
          new ReadableStream({
            start(controller) {
              for (let offset = 0; offset < bytes.length; offset += 7) {
                controller.enqueue(bytes.slice(offset, offset + 7));
              }
              controller.close();
            },
          }),
          { status: 200 },
        ),
      );
    });
    vi.stubGlobal('fetch', fetchMock);
    const stages: string[] = [];
    const deltas: string[] = [];
    const result = await streamAssistant(
      'سوال؟',
      'urdu',
      [],
      new AbortController().signal,
      {
        onStatus: (stage) => stages.push(stage),
        onDelta: (text) => deltas.push(text),
      },
    );
    expect(stages).toEqual(['retrieving']);
    expect(deltas).toEqual(['**جواب**']);
    expect(result.answer).toBe('**جواب**');
  });

  it('never displays a delta before verified start or accepts an incomplete stream', async () => {
    window.localStorage.setItem('ajt-fixture-identity', 'employee');
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(event('answer_delta', { text: 'unverified text' }), {
            status: 200,
          }),
        ),
      ),
    );
    const onDelta = vi.fn();
    await expect(
      streamAssistant(
        'Question?',
        'english',
        [],
        new AbortController().signal,
        {
          onStatus: vi.fn(),
          onDelta,
        },
      ),
    ).rejects.toThrow();
    expect(onDelta).not.toHaveBeenCalled();
  });
});
