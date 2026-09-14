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
