import type { AdminUser, CatalogItem } from '../../../types/admin';

export type UserCatalogs = {
  departments: CatalogItem[];
  locations: CatalogItem[];
  organizational_roles: CatalogItem[];
};

export type UserFormState = {
  display_name: string;
  email: string;
  preferred_language: 'english' | 'urdu' | 'roman_urdu';
  application_roles: ('employee' | 'sop_admin' | 'system_admin')[];
  departments: string[];
  locations: string[];
  organizational_roles: string[];
  management_departments: string[];
  management_locations: string[];
  management_roles: string[];
};

export const emptyUserForm: UserFormState = {
  display_name: '',
  email: '',
  preferred_language: 'english',
  application_roles: ['employee'],
  departments: [],
  locations: [],
  organizational_roles: [],
  management_departments: [],
  management_locations: [],
  management_roles: [],
};

const knownValues = (values: string[], items: CatalogItem[]) => {
  const keys = new Set(items.map((item) => item.key));
  return values.filter((value) => keys.has(value));
};

export function hasLegacyAssignments(user: AdminUser, catalogs: UserCatalogs) {
  return (
    user.departments.length !==
      knownValues(user.departments, catalogs.departments).length ||
    user.locations.length !==
      knownValues(user.locations, catalogs.locations).length ||
    user.organizational_roles.length !==
      knownValues(user.organizational_roles, catalogs.organizational_roles)
        .length ||
    user.management_departments.length !==
      knownValues(user.management_departments, catalogs.departments).length ||
    user.management_locations.length !==
      knownValues(user.management_locations, catalogs.locations).length ||
    user.management_roles.length !==
      knownValues(user.management_roles, catalogs.organizational_roles).length
  );
}

export function userToForm(
  user: AdminUser,
  catalogs: UserCatalogs,
): UserFormState {
  return {
    display_name: user.display_name,
    email: user.email,
    preferred_language:
      user.preferred_language === 'urdu' ||
      user.preferred_language === 'roman_urdu'
        ? user.preferred_language
        : 'english',
    application_roles: user.application_roles,
    departments: knownValues(user.departments, catalogs.departments),
    locations: knownValues(user.locations, catalogs.locations),
    organizational_roles: knownValues(
      user.organizational_roles,
      catalogs.organizational_roles,
    ),
    management_departments: knownValues(
      user.management_departments,
      catalogs.departments,
    ),
    management_locations: knownValues(
      user.management_locations,
      catalogs.locations,
    ),
    management_roles: knownValues(
      user.management_roles,
      catalogs.organizational_roles,
    ),
  };
}

export function formIsComplete(value: UserFormState) {
  const employeeScope =
    value.application_roles.includes('system_admin') ||
    value.departments.length > 0;
  const managementScope =
    !value.application_roles.includes('sop_admin') ||
    value.application_roles.includes('system_admin') ||
    value.management_departments.length > 0;
  return (
    value.display_name.trim().length > 0 &&
    value.email.includes('@') &&
    employeeScope &&
    managementScope
  );
}
