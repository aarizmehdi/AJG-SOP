import { z } from 'zod';
import { canonicalBlockSchema, sourceFormatSchema } from './source';

export const sourceLocatorSchema = z
  .object({
    source_document_id: z.string(),
    page_start: z.number().nullable(),
    page_end: z.number().nullable(),
    sheet_name: z.string().nullable(),
    cell_range: z.string().nullable(),
    block_anchor: z.string().nullable(),
  })
  .loose();

export const searchEvidenceSchema = z.object({
  organization_id: z.string(),
  chunk_id: z.string(),
  policy_id: z.string(),
  version_id: z.string(),
  section_id: z.string(),
  policy_title: z.string(),
  heading_path: z.array(z.string()),
  policy_number: z.string().nullable(),
  excerpt: z.string(),
  source: sourceLocatorSchema,
  fused_score: z.number(),
});
export const searchResponseSchema = z.object({
  results: z.array(searchEvidenceSchema),
  query: z.string(),
  language: z.string(),
});

export const readerSectionSchema = z.object({
  organization_id: z.string(),
  policy_id: z.string(),
  version_id: z.string(),
  section_id: z.string(),
  heading: z.string(),
  heading_path: z.array(z.string()),
  heading_level: z.number().default(1),
  parent_section_id: z.string().nullable().optional().default(null),
  chapter: z.string().nullable().optional().default(null),
  policy_number: z.string().nullable(),
  content: z.string(),
  blocks: z.array(canonicalBlockSchema).optional().default([]),
  source: sourceLocatorSchema,
});
export const readerSourceSchema = z.object({
  source_id: z.string(),
  file_name: z.string(),
  media_type: z.string(),
  source_format: sourceFormatSchema,
});
export const policyReaderSchema = z.object({
  policy_id: z.string(),
  title: z.string(),
  category: z.string(),
  version_label: z.string(),
  sections: z.array(readerSectionSchema),
  original_download_allowed: z.boolean(),
  original_sources: z.array(readerSourceSchema).optional().default([]),
});
export type PolicyReader = z.infer<typeof policyReaderSchema>;
export type ReaderSource = z.infer<typeof readerSourceSchema>;

export const availablePolicySchema = z.object({
  policy_id: z.string(),
  title: z.string(),
  policy_number: z.string().nullable(),
  category: z.string(),
  version_label: z.string(),
  effective_date: z.string().nullable(),
  updated_at: z.string(),
  recently_updated: z.boolean(),
});
export const availablePolicyListSchema = z.array(availablePolicySchema);
export type AvailablePolicy = z.infer<typeof availablePolicySchema>;
