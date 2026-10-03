import { describe, expect, it } from 'vitest';
import { emptyUserForm, formIsComplete } from './userForm';

const employeeScope = {
  departments: ['store'],
  locations: ['mill-1'],
  organizational_roles: ['store_keeper'],
};

describe('system administrator user form', () => {
  it('requires identity and a department', () => {
    expect(formIsComplete(emptyUserForm)).toBe(false);
    expect(
      formIsComplete({
        ...emptyUserForm,
        ...employeeScope,
        display_name: 'Test Employee',
        email: 'employee@example.test',
      }),
    ).toBe(true);
  });

  it('allows creation and editing with empty optional employee assignments', () => {
    const employee = {
      ...emptyUserForm,
      display_name: 'Department-only employee',
      email: 'employee@example.test',
      departments: ['store'],
    };
    expect(formIsComplete(employee)).toBe(true);
    expect(formIsComplete({ ...employee, departments: [] })).toBe(false);
    expect(
      formIsComplete({
        ...employee,
        application_roles: ['employee', 'sop_admin', 'system_admin'],
      }),
    ).toBe(true);
  });

  it('requires all management dimensions for a scoped SOP Administrator', () => {
    const sopAdmin = {
      ...emptyUserForm,
      ...employeeScope,
      display_name: 'SOP Administrator',
      email: 'sop-admin@example.test',
      application_roles: ['employee', 'sop_admin'] as const,
    };
    expect(
      formIsComplete({
        ...sopAdmin,
        application_roles: [...sopAdmin.application_roles],
      }),
    ).toBe(false);
    expect(
      formIsComplete({
        ...sopAdmin,
        application_roles: [...sopAdmin.application_roles],
        management_departments: ['store'],
        management_locations: ['mill-1'],
        management_roles: ['store_keeper'],
      }),
    ).toBe(true);
  });
});
