import { z } from 'zod';
import { sourceLocatorSchema } from './retrieval';

export const citationSchema = z.object({
  chunk_id: z.string(),
  policy_id: z.string(),
  policy_title: z.string(),
  section_id: z.string(),
  heading_path: z.array(z.string()),
  document_id: z.string(),
  source: sourceLocatorSchema,
});
export const verifiedAnswerSchema = z.object({
  organization_id: z.string(),
  answerable: z.boolean(),
  answer: z.string(),
  language: z.enum(['english', 'urdu', 'roman_urdu']),
  citations: z.array(citationSchema),
  verified: z.boolean(),
  session_id: z.string(),
});
export type VerifiedAnswer = z.infer<typeof verifiedAnswerSchema>;
