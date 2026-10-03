import { z } from 'zod';
import { apiStream } from '../../api/client';
import {
  streamSourcesSchema,
  streamStartSchema,
  type StreamAnswer,
} from '../../types/assistant';

const statusSchema = z.object({
  stage: z.enum([
    'retrieving',
    'reading',
    'generating',
    'repairing',
    'verifying',
  ]),
});
const deltaSchema = z.object({ text: z.string() });
const doneSchema = z.object({ verified: z.literal(true) });

type Callbacks = {
  onStatus: (stage: z.infer<typeof statusSchema>['stage']) => void;
  onDelta: (text: string) => void;
};

export async function streamAssistant(
  question: string,
  language: 'english' | 'urdu' | 'roman_urdu',
  history: { role: 'user' | 'assistant'; content: string }[],
  signal: AbortSignal,
  callbacks: Callbacks,
): Promise<StreamAnswer> {
  const response = await apiStream('/assistant/answer/events', {
    method: 'POST',
    body: JSON.stringify({ question, language, history: history.slice(-16) }),
    signal,
  });
  if (!response.body) throw new Error('Assistant stream is unavailable');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let started: z.infer<typeof streamStartSchema> | null = null;
  let answer = '';
  let citations: StreamAnswer['citations'] = [];
  const state = { finished: false };

  const processBlock = (block: string) => {
    const lines = block.split('\n');
    const name = lines
      .find((line) => line.startsWith('event:'))
      ?.slice(6)
      .trim();
    const dataText = lines
      .filter((line) => line.startsWith('data:'))
      .map((line) => line.slice(5).trimStart())
      .join('\n');
    if (!name || !dataText) return;
    const data: unknown = JSON.parse(dataText);
    if (name === 'status') callbacks.onStatus(statusSchema.parse(data).stage);
    if (name === 'answer_start') {
      const parsed = streamStartSchema.parse(data);
      if (!parsed.verified || parsed.language !== language || started)
        throw new Error('Invalid verified answer');
      started = parsed;
    }
    if (name === 'answer_delta') {
      if (!started || state.finished)
        throw new Error('Answer arrived before verification');
      const text = deltaSchema.parse(data).text;
      answer += text;
      callbacks.onDelta(text);
    }
    if (name === 'sources') {
      if (!started) throw new Error('Sources arrived before verification');
      citations = [
        ...new Map(
          streamSourcesSchema
            .parse(data)
            .citations.map((citation) => [citation.chunk_id, citation]),
        ).values(),
      ];
    }
    if (name === 'done') {
      doneSchema.parse(data);
      if (!started) throw new Error('Answer did not pass verification');
      state.finished = true;
    }
    if (name === 'error') throw new Error('Assistant answer unavailable');
  };

  try {
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, '\n');
      let boundary = buffer.indexOf('\n\n');
      while (boundary >= 0) {
        processBlock(buffer.slice(0, boundary));
        buffer = buffer.slice(boundary + 2);
        boundary = buffer.indexOf('\n\n');
      }
    }
    if (!state.finished)
      throw new Error('Assistant stream ended before verification');
    return { ...streamStartSchema.parse(started), answer, citations };
  } finally {
    reader.releaseLock();
  }
}
