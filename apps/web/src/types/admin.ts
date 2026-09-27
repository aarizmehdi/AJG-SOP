import { z } from 'zod';
import { profileSchema } from './profile';

export const catalogKindSchema = z.enum([
  'departments',
  'locations',
  'organizational_roles',
]);
export type CatalogKind = z.infer<typeof catalogKindSchema>;

export const catalogItemSchema = z.object({
  id: z.string(),
  organization_id: z.string(),
  key: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  active: z.boolean(),
  version: z.number(),
  created_at: z.string(),
  updated_at: z.string(),
  usage: z
    .object({
      active_users: z.number(),
      policies: z.number(),
      sop_administrators: z.number(),
      total: z.number(),
    })
    .optional(),
});
export const catalogListSchema = z.array(catalogItemSchema);
export type CatalogItem = z.infer<typeof catalogItemSchema>;

export const adminUserSchema = profileSchema.extend({
  identity_subject: z.string(),
  created_at: z.string(),
  updated_at: z.string(),
  identity_linked: z.boolean().optional(),
});
export type AdminUser = z.infer<typeof adminUserSchema>;

export const userPageSchema = z.object({
  items: z.array(adminUserSchema),
  total: z.number(),
  page: z.number(),
  limit: z.number(),
});

export const createdUserSchema = z.object({
  user: adminUserSchema,
  activation_link: z.string(),
});

export const resetLinkSchema = z.object({
  message: z.string(),
  reset_link: z.string(),
});

export const auditEventSchema = z.object({
  id: z.string(),
  organization_id: z.string(),
  actor_id: z.string(),
  action: z.string(),
  entity_type: z.string(),
  entity_id: z.string(),
  occurred_at: z.string(),
  metadata: z.record(z.string(), z.unknown()),
});
export const auditPageSchema = z.object({
  items: z.array(auditEventSchema),
  total: z.number(),
  page: z.number(),
  limit: z.number(),
});

export const overviewSchema = z.object({
  users: z.object({
    active: z.number(),
    employees: z.number(),
    sop_administrators: z.number(),
    system_administrators: z.number(),
  }),
  catalogs: z.object({
    departments: z.number(),
    locations: z.number(),
    organizational_roles: z.number(),
  }),
  policies: z.object({
    published: z.number(),
    review_required: z.number(),
    failed_jobs: z.number(),
  }),
  recent_activity: z.array(auditEventSchema),
});

export const organizationSummarySchema = z.object({
  organization_id: z.string(),
  name: z.string(),
  catalog_counts: z.object({
    departments: z.number(),
    locations: z.number(),
    organizational_roles: z.number(),
  }),
});

const accessCheckSchema = z.object({
  policy_mode: z.enum(['all', 'selected']),
  policy_values: z.array(z.string()),
  user_values: z.array(z.string()),
  matched_values: z.array(z.string()),
  allowed: z.boolean(),
});
export const accessInspectionSchema = z.object({
  user: z.object({
    id: z.string(),
    display_name: z.string(),
    email: z.string(),
  }),
  policy: z.object({
    id: z.string(),
    title: z.string(),
    policy_number: z.string().nullable(),
  }),
  dimensions: z.object({
    departments: accessCheckSchema,
    locations: accessCheckSchema,
    organizational_roles: accessCheckSchema,
  }),
  authorized: z.boolean(),
});
