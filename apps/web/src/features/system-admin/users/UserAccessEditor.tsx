import { CatalogMultiSelect } from '../CatalogMultiSelect';
import { useOrganizationCatalogs } from '../catalogs';
import type { UserFormState } from './userForm';

export function UserAccessEditor({
  value,
  onChange,
}: {
  value: UserFormState;
  onChange: (value: UserFormState) => void;
}) {
  const catalogs = useOrganizationCatalogs(true);
  const update = <K extends keyof UserFormState>(
    field: K,
    next: UserFormState[K],
  ) => {
    onChange({ ...value, [field]: next });
  };
  const accountType = value.application_roles.includes('system_admin')
    ? 'system_admin'
    : value.application_roles.includes('sop_admin')
      ? 'sop_admin'
      : 'employee';
  const setAccountType = (type: string) => {
    onChange({
      ...value,
      application_roles:
        type === 'system_admin'
          ? ['employee', 'sop_admin', 'system_admin']
          : type === 'sop_admin'
            ? ['employee', 'sop_admin']
            : ['employee'],
      management_departments:
        type === 'sop_admin' ? value.management_departments : [],
      management_locations:
        type === 'sop_admin' ? value.management_locations : [],
      management_roles: type === 'sop_admin' ? value.management_roles : [],
    });
  };
  return (
    <div className="user-form-sections">
      <section className="surface user-form-section">
        <div className="form-section-heading">
          <span>01</span>
          <div>
            <h3>Identity</h3>
            <p>Firebase owns authentication; AJG SOP stores no password.</p>
          </div>
        </div>
        <div className="form-grid">
          <label>
            Full name
            <input
              autoComplete="name"
              value={value.display_name}
              onChange={(event) => {
                update('display_name', event.target.value);
              }}
            />
          </label>
          <label>
            Email address
            <input
              type="email"
              autoComplete="email"
              value={value.email}
              onChange={(event) => {
                update('email', event.target.value);
              }}
            />
          </label>
          <label>
            Preferred language
            <select
              value={value.preferred_language}
              onChange={(event) => {
                update(
                  'preferred_language',
                  event.target.value as UserFormState['preferred_language'],
                );
              }}
            >
              <option value="english">English</option>
              <option value="urdu">Urdu</option>
              <option value="roman_urdu">Roman Urdu</option>
            </select>
          </label>
        </div>
      </section>
      <section className="surface user-form-section">
        <div className="form-section-heading">
          <span>02</span>
          <div>
            <h3>Application access</h3>
            <p>Choose what the person may do inside AJG SOP.</p>
          </div>
        </div>
        <div className="role-choice-grid">
          {(
            [
              [
                'employee',
                'Employee',
                'Read, search, and ask about authorized SOPs.',
              ],
              [
                'sop_admin',
                'SOP Administrator',
                'Review SOPs inside an assigned management scope.',
              ],
              [
                'system_admin',
                'System Administrator',
                'Organization-wide administration for AJT.',
              ],
            ] as const
          ).map(([id, label, description]) => (
            <label
              className={`role-choice${accountType === id ? ' selected' : ''}`}
              key={id}
            >
              <input
                type="radio"
                name="account-type"
                value={id}
                checked={accountType === id}
                onChange={() => {
                  setAccountType(id);
                }}
              />
              <strong>{label}</strong>
              <span>{description}</span>
            </label>
          ))}
        </div>
      </section>
      <section className="surface user-form-section">
        <div className="form-section-heading">
          <span>03</span>
          <div>
            <h3>Employee scope</h3>
            <p>Used for policy reading, search, and assistant authorization.</p>
          </div>
        </div>
        {catalogs.isPending ? (
          <p role="status">Loading organization options…</p>
        ) : catalogs.isError ? (
          <p className="form-error">
            Organization catalogs could not be loaded.
          </p>
        ) : (
          <div className="scope-catalog-grid">
            <CatalogMultiSelect
              label="Departments"
              items={catalogs.data.departments}
              value={value.departments}
              onChange={(next) => {
                update('departments', next);
              }}
            />
            <CatalogMultiSelect
              label="Locations"
              items={catalogs.data.locations}
              value={value.locations}
              onChange={(next) => {
                update('locations', next);
              }}
            />
            <CatalogMultiSelect
              label="Organizational roles"
              items={catalogs.data.organizational_roles}
              value={value.organizational_roles}
              onChange={(next) => {
                update('organizational_roles', next);
              }}
            />
          </div>
        )}
      </section>
      {accountType === 'sop_admin' && (
        <section className="surface user-form-section management-section">
          <div className="form-section-heading">
            <span>04</span>
            <div>
              <h3>Management scope</h3>
              <p>
                Defines which SOP access scopes this administrator may manage.
                It does not grant organization-wide administration.
              </p>
            </div>
          </div>
          {catalogs.data && (
            <div className="scope-catalog-grid">
              <CatalogMultiSelect
                label="Managed departments"
                items={catalogs.data.departments}
                value={value.management_departments}
                onChange={(next) => {
                  update('management_departments', next);
                }}
              />
              <CatalogMultiSelect
                label="Managed locations"
                items={catalogs.data.locations}
                value={value.management_locations}
                onChange={(next) => {
                  update('management_locations', next);
                }}
              />
              <CatalogMultiSelect
                label="Managed organizational roles"
                items={catalogs.data.organizational_roles}
                value={value.management_roles}
                onChange={(next) => {
                  update('management_roles', next);
                }}
              />
            </div>
          )}
        </section>
      )}
    </div>
  );
}
