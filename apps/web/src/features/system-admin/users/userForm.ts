import type { AdminUser } from '../../../types/admin';

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

export function userToForm(user: AdminUser): UserFormState {
  return {
    display_name: user.display_name,
    email: user.email,
    preferred_language:
      user.preferred_language === 'urdu' ||
      user.preferred_language === 'roman_urdu'
        ? user.preferred_language
        : 'english',
    application_roles: user.application_roles,
    departments: user.departments,
    locations: user.locations,
    organizational_roles: user.organizational_roles,
    management_departments: user.management_departments,
    management_locations: user.management_locations,
    management_roles: user.management_roles,
  };
}

export function formIsComplete(value: UserFormState) {
  const employeeScope =
    value.departments.length > 0 &&
    value.locations.length > 0 &&
    value.organizational_roles.length > 0;
  const managementScope =
    !value.application_roles.includes('sop_admin') ||
    value.application_roles.includes('system_admin') ||
    (value.management_departments.length > 0 &&
      value.management_locations.length > 0 &&
      value.management_roles.length > 0);
  return (
    value.display_name.trim().length > 0 &&
    value.email.includes('@') &&
    employeeScope &&
    managementScope
  );
}
