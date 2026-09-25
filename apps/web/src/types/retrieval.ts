import { z } from 'zod';

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
  policy_number: z.string().nullable(),
  content: z.string(),
  source: sourceLocatorSchema,
});
export const policyReaderSchema = z.object({
  policy_id: z.string(),
  title: z.string(),
  category: z.string(),
  version_label: z.string(),
  sections: z.array(readerSectionSchema),
  original_download_allowed: z.boolean(),
});

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
