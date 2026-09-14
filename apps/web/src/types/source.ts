import { z } from 'zod';

export const sourceFormatSchema = z.enum([
  'pdf',
  'scanned_pdf',
  'image',
  'docx',
  'xlsx',
  'markdown',
  'structured_text',
]);
export type SourceFormat = z.infer<typeof sourceFormatSchema>;
export const parserCapabilitySchema = z.object({
  organization_id: z.string(),
  provider: z.string(),
  source_format: sourceFormatSchema,
  available: z.boolean(),
  detail: z.string(),
});
export const parserCapabilitiesSchema = z.array(parserCapabilitySchema);

export const sourceDocumentSchema = z.object({
  id: z.string(),
  organization_id: z.string(),
  policy_id: z.string(),
  version_id: z.string(),
  file_name: z.string(),
  media_type: z.string(),
  source_format: sourceFormatSchema,
  sha256: z.string(),
  original_artifact_uri: z.string(),
  status: z.enum([
    'uploaded',
    'processing',
    'review_required',
    'approved',
    'failed',
  ]),
  parser_provider: z.string().nullable(),
  parser_version: z.string().nullable(),
  raw_artifact_uri: z.string().nullable(),
  canonical_artifact_uri: z.string().nullable(),
  reviewed_artifact_uri: z.string().nullable(),
  error_code: z.string().nullable(),
  created_at: z.string(),
});

const sourceLocatorSchema = z.object({
  source_document_id: z.string(),
  page_start: z.number().nullable(),
  page_end: z.number().nullable(),
  bounding_boxes: z.array(
    z.object({
      x: z.number(),
      y: z.number(),
      width: z.number(),
      height: z.number(),
      unit: z.string(),
    }),
  ),
  text_start: z.number().nullable(),
  text_end: z.number().nullable(),
  sheet_name: z.string().nullable(),
  cell_range: z.string().nullable(),
  block_anchor: z.string().nullable(),
});

export const canonicalBlockSchema = z
  .object({
    id: z.string(),
    kind: z.enum(['paragraph', 'ordered_list', 'unordered_list', 'table']),
    text: z.string().nullable(),
    list_items: z.array(
      z
        .object({
          text: z.string(),
          level: z.number(),
          marker: z.string().nullable(),
          children: z.array(z.unknown()),
          source: sourceLocatorSchema,
        })
        .loose(),
    ),
    table: z
      .object({
        cells: z.array(
          z
            .object({
              text: z.string(),
              row: z.number(),
              column: z.number(),
              row_span: z.number(),
              column_span: z.number(),
              is_header: z.boolean(),
              source: sourceLocatorSchema,
            })
            .loose(),
        ),
      })
      .loose()
      .nullable(),
    source: sourceLocatorSchema,
  })
  .loose();

export const canonicalSectionSchema = z
  .object({
    id: z.string(),
    stable_key: z.string(),
    heading: z.string(),
    heading_level: z.number(),
    heading_path: z.array(z.string()),
    policy_number: z.string().nullable(),
    blocks: z.array(canonicalBlockSchema),
    source: sourceLocatorSchema,
  })
  .loose();

export const canonicalSopSchema = z
  .object({
    id: z.string(),
    organization_id: z.string(),
    policy_id: z.string(),
    version_id: z.string(),
    title: z.string(),
    sections: z.array(canonicalSectionSchema),
    approved: z.boolean(),
  })
  .loose();

export const rawDocumentSchema = z
  .object({
    title: z.string(),
    blocks: z.array(
      z
        .object({
          kind: z.string(),
          text: z.string(),
          page: z.number().nullable(),
          sheet_name: z.string().nullable(),
          cell_range: z.string().nullable(),
          table_cells: z.array(
            z
              .object({
                text: z.string(),
                row: z.number(),
                column: z.number(),
                cell_reference: z.string().nullable(),
              })
              .loose(),
          ),
        })
        .loose(),
    ),
    warnings: z.array(z.string()),
  })
  .loose();
export const reviewPayloadSchema = z.object({
  source: sourceDocumentSchema,
  canonical: canonicalSopSchema.nullable(),
  raw: rawDocumentSchema.nullable(),
});
