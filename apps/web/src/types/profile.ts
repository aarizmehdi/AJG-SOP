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
  preferred_language: z.string().nullable(),
});
