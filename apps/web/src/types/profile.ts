import { z } from 'zod';

export const profileSchema = z.object({
  id: z.string(),
  organization_id: z.string(),
  display_name: z.string(),
  email: z.string(),
  application_roles: z.array(z.enum(['employee', 'sop_admin', 'system_admin'])),
  departments: z.array(z.string()),
  locations: z.array(z.string()),
  organizational_roles: z.array(z.string()),
  management_departments: z.array(z.string()).default([]),
  management_locations: z.array(z.string()).default([]),
  management_roles: z.array(z.string()).default([]),
  preferred_language: z.string().nullable(),
  active: z.boolean().default(true),
  status: z
    .enum(['pending_activation', 'active', 'disabled'])
    .default('active'),
  version: z.number().default(1),
});

export type Profile = z.infer<typeof profileSchema>;
