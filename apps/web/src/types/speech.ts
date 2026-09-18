import { z } from 'zod';

export const speechTranscriptionSchema = z.object({
  detected_language: z.string(),
  raw_transcript: z.string(),
  normalized_transcript: z.string(),
});

export type SpeechTranscription = z.infer<typeof speechTranscriptionSchema>;
