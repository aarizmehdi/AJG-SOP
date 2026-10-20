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
export const sectionOptionSchema = citationSchema
  .omit({ chunk_id: true, document_id: true })
  .extend({ version_id: z.string(), heading: z.string() });
export const verifiedAnswerSchema = z.object({
  organization_id: z.string(),
  kind: z
    .enum([
      'smalltalk',
      'policy_answer',
      'clarification',
      'no_answer',
      'out_of_scope',
    ])
    .default('policy_answer'),
  answerable: z.boolean(),
  answer: z.string(),
  language: z.enum(['english', 'urdu', 'roman_urdu']),
  citations: z.array(citationSchema),
  verified: z.boolean(),
  section_options: z.array(sectionOptionSchema).max(8).default([]),
});
export type VerifiedAnswer = z.infer<typeof verifiedAnswerSchema>;

export const streamStartSchema = verifiedAnswerSchema.pick({
  kind: true,
  answerable: true,
  language: true,
  verified: true,
});
export const streamSourcesSchema = z.object({
  citations: z.array(citationSchema),
  section_options: z.array(sectionOptionSchema).max(8).default([]),
});
export type StreamAnswer = z.infer<typeof streamStartSchema> & {
  answer: string;
  citations: z.infer<typeof citationSchema>[];
  section_options: z.infer<typeof sectionOptionSchema>[];
};
