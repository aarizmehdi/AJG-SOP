import { z } from 'zod';

export const accessDimensionSchema = z.object({
  mode: z.enum(['all', 'selected']),
  values: z.array(z.string()),
});
export const accessScopeSchema = z.object({
  departments: accessDimensionSchema,
  locations: accessDimensionSchema,
  roles: accessDimensionSchema,
});
export type AccessScope = z.infer<typeof accessScopeSchema>;

export const versionSchema = z.object({
  id: z.string(),
  organization_id: z.string(),
  policy_id: z.string(),
  version_label: z.string(),
  status: z.string(),
  access: accessScopeSchema,
  source_document_ids: z.array(z.string()),
  source_names: z.array(z.string()).optional(),
  canonical_document_ids: z.array(z.string()),
  index_revision: z.string().nullable(),
  created_at: z.string(),
  published_at: z.string().nullable(),
  effective_date: z.string().nullable(),
});
export const policySchema = z.object({
  id: z.string(),
  organization_id: z.string(),
  title: z.string(),
  category: z.string(),
  policy_number: z.string().nullable(),
  status: z.string(),
  active_version_id: z.string().nullable(),
  created_at: z.string(),
  updated_at: z.string(),
  versions: z.array(versionSchema).optional(),
  display_version_id: z.string().optional(),
  sources: z
    .array(
      z.object({
        id: z.string(),
        file_name: z.string(),
        media_type: z.string(),
        source_format: z.string(),
        status: z.string(),
        created_at: z.string(),
      }),
    )
    .optional(),
  section_count: z.number().optional(),
  page_count: z.number().nullable().optional(),
});
export type Policy = z.infer<typeof policySchema>;
export const policyListSchema = z.array(policySchema);
export const policyDraftSchema = z.object({
  policy: policySchema,
  version: versionSchema,
});
export const sectionChangeSchema = z.object({
  organization_id: z.string(),
  kind: z.enum(['added', 'removed', 'changed']),
  stable_key: z.string(),
  heading: z.string(),
  old_content: z.string().nullable(),
  new_content: z.string().nullable(),
  access_changed: z.boolean(),
});
export const sectionChangesSchema = z.array(sectionChangeSchema);

export const viewerSchema = z.object({
  policy: policySchema,
  version: versionSchema,
  versions: z.array(versionSchema),
  sources: z.array(
    z.object({
      id: z.string(),
      file_name: z.string(),
      media_type: z.string(),
      source_format: z.string(),
      status: z.string(),
      created_at: z.string(),
      original_allowed: z.boolean(),
    }),
  ),
  canonicals: z.array(
    z
      .object({
        id: z.string(),
        title: z.string(),
        policy_number: z.string().nullable().optional().default(null),
        effective_date: z.string().nullable().optional().default(null),
        approved: z.boolean(),
        sections: z.array(
          z
            .object({
              id: z.string(),
              stable_key: z.string(),
              heading: z.string(),
              heading_level: z.number(),
              chapter: z.string().nullable(),
              parent_section_id: z.string().nullable(),
              heading_path: z.array(z.string()),
              policy_number: z.string().nullable(),
              source: z
                .object({
                  source_document_id: z.string(),
                  page_start: z.number().nullable(),
                  page_end: z.number().nullable(),
                  sheet_name: z.string().nullable(),
                  cell_range: z.string().nullable(),
                })
                .loose(),
              blocks: z.array(
                z
                  .object({
                    id: z.string(),
                    kind: z.enum([
                      'paragraph',
                      'ordered_list',
                      'unordered_list',
                      'table',
                    ]),
                    text: z.string().nullable(),
                    list_items: z.array(z.unknown()),
                    table: z
                      .object({
                        caption: z.string().nullable(),
                        cells: z.array(
                          z
                            .object({
                              text: z.string(),
                              row: z.number(),
                              column: z.number(),
                              row_span: z.number(),
                              column_span: z.number(),
                              is_header: z.boolean(),
                            })
                            .loose(),
                        ),
                      })
                      .loose()
                      .nullable(),
                  })
                  .loose(),
              ),
            })
            .loose(),
        ),
      })
      .loose(),
  ),
  section_count: z.number(),
  page_count: z.number().nullable(),
});
export type PolicyViewer = z.infer<typeof viewerSchema>;
