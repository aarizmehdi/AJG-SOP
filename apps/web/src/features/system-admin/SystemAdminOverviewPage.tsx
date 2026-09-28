import { useQuery } from '@tanstack/react-query';
import {
  BookOpenCheck,
  Building2,
  MapPin,
  ShieldCheck,
  Tags,
  UserCog,
  Users,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { overviewSchema } from '../../types/admin';
import { systemAdminErrorDetail } from './errorDetail';

export default function SystemAdminOverviewPage() {
  const overview = useQuery({
    queryKey: ['system-admin-overview'],
    queryFn: () => apiRequest('/admin/overview', overviewSchema),
  });
  if (overview.isPending)
    return <RouteSkeleton label="Loading administration overview" />;
  if (overview.isError)
    return (
      <ErrorState
        title="Overview unavailable"
        detail={systemAdminErrorDetail(overview.error)}
      />
    );
  const cards = [
    {
      label: 'Active users',
      value: overview.data.users.active,
      icon: Users,
      to: '/admin/users',
    },
    {
      label: 'Employees',
      value: overview.data.users.employees,
      icon: Users,
      to: '/admin/users?application_role=employee',
    },
    {
      label: 'SOP administrators',
      value: overview.data.users.sop_administrators,
      icon: UserCog,
      to: '/admin/users?application_role=sop_admin',
    },
    {
      label: 'System administrators',
      value: overview.data.users.system_administrators,
      icon: ShieldCheck,
      to: '/admin/users?application_role=system_admin',
    },
    {
      label: 'Departments',
      value: overview.data.catalogs.departments,
      icon: Building2,
      to: '/admin/departments',
    },
    {
      label: 'Locations',
      value: overview.data.catalogs.locations,
      icon: MapPin,
      to: '/admin/locations',
    },
    {
      label: 'Organizational roles',
      value: overview.data.catalogs.organizational_roles,
      icon: Tags,
      to: '/admin/organizational-roles',
    },
    {
      label: 'Published SOPs',
      value: overview.data.policies.published,
      icon: BookOpenCheck,
      to: '/admin/policies',
    },
  ];
  return (
    <section className="control-section">
      <div className="control-section-heading">
        <div>
          <span className="eyebrow">Organization status</span>
          <h2>Overview</h2>
          <p>Live counts from AJT identity, access, and policy records.</p>
        </div>
        <Link className="button button--primary" to="/admin/users/new">
          Create user
        </Link>
      </div>
      <div className="metric-grid">
        {cards.map(({ label, value, icon: Icon, to }) => (
          <Link className="metric-card" to={to} key={label}>
            <Icon size={20} aria-hidden="true" />
            <strong>{value}</strong>
            <span>{label}</span>
          </Link>
        ))}
        <div className="metric-card metric-card--review">
          <span className="metric-dot" />
          <strong>{overview.data.policies.review_required}</strong>
          <span>Draft / review required</span>
        </div>
        <div className="metric-card metric-card--failed">
          <span className="metric-dot" />
          <strong>{overview.data.policies.failed_jobs}</strong>
          <span>Failed processing jobs</span>
        </div>
      </div>
      <section className="surface activity-panel">
        <div className="panel-heading">
          <div>
            <h3>Recent administrative activity</h3>
            <p>Tenant-scoped security and organization changes.</p>
          </div>
          <Link to="/admin/audit">View audit log</Link>
        </div>
        {!overview.data.recent_activity.length ? (
          <p className="empty-copy">
            No administrative activity has been recorded yet.
          </p>
        ) : (
          <div className="activity-list">
            {overview.data.recent_activity.map((event) => (
              <div className="activity-row" key={event.id}>
                <span className="activity-marker" />
                <div>
                  <strong>
                    {event.action.replaceAll('.', ' · ').replaceAll('_', ' ')}
                  </strong>
                  <small>
                    {event.entity_type} · {event.entity_id}
                  </small>
                </div>
                <time dateTime={event.occurred_at}>
                  {new Intl.DateTimeFormat(undefined, {
                    dateStyle: 'medium',
                    timeStyle: 'short',
                  }).format(new Date(event.occurred_at))}
                </time>
              </div>
            ))}
          </div>
        )}
      </section>
    </section>
  );
}
