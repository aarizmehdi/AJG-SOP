import { useQuery } from '@tanstack/react-query';
import { z } from 'zod';
import { apiRequest } from '../../api/client';
import { catalogItemSchema } from '../../types/admin';

const catalogsSchema = z.object({
  departments: z.array(catalogItemSchema),
  locations: z.array(catalogItemSchema),
  organizational_roles: z.array(catalogItemSchema),
});

export function useOrganizationCatalogs(includeInactive = false) {
  return useQuery({
    queryKey: ['organization-catalogs', includeInactive],
    queryFn: async () => {
      const query = `?include_inactive=${includeInactive ? 'true' : 'false'}`;
      const [departments, locations, organizationalRoles] = await Promise.all([
        apiRequest(`/admin/departments${query}`, z.array(catalogItemSchema)),
        apiRequest(`/admin/locations${query}`, z.array(catalogItemSchema)),
        apiRequest(
          `/admin/organizational_roles${query}`,
          z.array(catalogItemSchema),
        ),
      ]);
      return catalogsSchema.parse({
        departments,
        locations,
        organizational_roles: organizationalRoles,
      });
    },
  });
}
