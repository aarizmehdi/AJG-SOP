import { useQuery } from '@tanstack/react-query';
import { ChevronRight, Plus, Search, Users } from 'lucide-react';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../../api/client';
import { ErrorState } from '../../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../../components/feedback/RouteSkeleton';
import { userPageSchema } from '../../../types/admin';
import { useOrganizationCatalogs } from '../catalogs';

export default function UserListPage() {
  const [params, setParams] = useSearchParams();
  const [search, setSearch] = useState(params.get('search') ?? '');
  const catalogs = useOrganizationCatalogs(true);
  const queryString = params.toString();
  const users = useQuery({
    queryKey: ['admin-users', queryString],
    queryFn: () =>
      apiRequest(
        `/admin/users${queryString ? `?${queryString}` : ''}`,
        userPageSchema,
      ),
  });
  const updateFilter = (name: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    next.delete('page');
    setParams(next);
  };
  if (users.isPending)
    return <RouteSkeleton label="Loading organization users" />;
  if (users.isError)
    return (
      <ErrorState
        title="Users unavailable"
        detail="Only a System Administrator can inspect organization users."
      />
    );
  return (
    <section className="control-section">
      <div className="control-section-heading">
        <div>
          <span className="eyebrow">People & access</span>
          <h2>Users</h2>
          <p>{users.data.total} tenant-scoped identity records</p>
        </div>
        <Link className="button button--primary" to="/admin/users/new">
          <Plus size={17} /> Create user
        </Link>
      </div>
      <div className="surface user-toolbar">
        <form
          className="admin-search"
          onSubmit={(event) => {
            event.preventDefault();
            updateFilter('search', search.trim());
          }}
        >
          <Search size={17} aria-hidden="true" />
          <input
            aria-label="Search users"
            placeholder="Search name or email"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
            }}
          />
        </form>
        <select
          aria-label="Filter by status"
          value={params.get('status') ?? ''}
          onChange={(event) => {
            updateFilter('status', event.target.value);
          }}
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="pending_activation">Pending activation</option>
          <option value="disabled">Disabled</option>
        </select>
        <select
          aria-label="Filter by application role"
          value={params.get('application_role') ?? ''}
          onChange={(event) => {
            updateFilter('application_role', event.target.value);
          }}
        >
          <option value="">All application roles</option>
          <option value="employee">Employee</option>
          <option value="sop_admin">SOP Administrator</option>
          <option value="system_admin">System Administrator</option>
        </select>
        <select
          aria-label="Filter by department"
          value={params.get('department') ?? ''}
          onChange={(event) => {
            updateFilter('department', event.target.value);
          }}
        >
          <option value="">All departments</option>
          {catalogs.data?.departments.map((item) => (
            <option value={item.key} key={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by location"
          value={params.get('location') ?? ''}
          onChange={(event) => {
            updateFilter('location', event.target.value);
          }}
        >
          <option value="">All locations</option>
          {catalogs.data?.locations.map((item) => (
            <option value={item.key} key={item.id}>
              {item.name}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by organizational role"
          value={params.get('organizational_role') ?? ''}
          onChange={(event) => {
            updateFilter('organizational_role', event.target.value);
          }}
        >
          <option value="">All organizational roles</option>
          {catalogs.data?.organizational_roles.map((item) => (
            <option value={item.key} key={item.id}>
              {item.name}
            </option>
          ))}
        </select>
      </div>
      {!users.data.items.length ? (
        <div className="surface control-empty">
          <Users />
          <h3>No users match these filters</h3>
          <p>Clear a filter or create a new organization member.</p>
        </div>
      ) : (
        <div className="surface user-table-wrap">
          <table className="user-table">
            <thead>
              <tr>
                <th>User</th>
                <th>Application role</th>
                <th>Department</th>
                <th>Location</th>
                <th>Organizational role</th>
                <th>Status</th>
                <th>
                  <span className="sr-only">Open</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {users.data.items.map((user) => (
                <tr key={user.id}>
                  <td>
                    <strong>{user.display_name}</strong>
                    <small>{user.email}</small>
                  </td>
                  <td>
                    {user.application_roles.includes('system_admin')
                      ? 'System Administrator'
                      : user.application_roles.includes('sop_admin')
                        ? 'SOP Administrator'
                        : 'Employee'}
                  </td>
                  <td>{user.departments.join(', ') || '—'}</td>
                  <td>{user.locations.join(', ') || '—'}</td>
                  <td>{user.organizational_roles.join(', ') || '—'}</td>
                  <td>
                    <span className={`status-text ${user.status}`}>
                      {user.status.replace('_', ' ')}
                    </span>
                  </td>
                  <td>
                    <Link
                      aria-label={`Open ${user.display_name}`}
                      to={`/admin/users/${user.id}`}
                    >
                      <ChevronRight />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
