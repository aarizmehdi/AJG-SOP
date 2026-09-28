import { useQuery } from '@tanstack/react-query';
import { Building2, MapPin, Tags } from 'lucide-react';
import { apiRequest } from '../../../api/client';
import { ErrorState } from '../../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../../components/feedback/RouteSkeleton';
import { organizationSummarySchema } from '../../../types/admin';
import { systemAdminErrorDetail } from '../errorDetail';

export default function OrganizationSettingsPage() {
  const organization = useQuery({
    queryKey: ['admin-organization'],
    queryFn: () => apiRequest('/admin/organization', organizationSummarySchema),
  });
  if (organization.isPending)
    return <RouteSkeleton label="Loading organization settings" />;
  if (organization.isError)
    return (
      <ErrorState
        title="Organization unavailable"
        detail={systemAdminErrorDetail(
          organization.error,
          'The organization record could not be loaded.',
        )}
      />
    );
  const catalogCards = [
    ['Departments', organization.data.catalog_counts.departments, Building2],
    ['Locations', organization.data.catalog_counts.locations, MapPin],
    [
      'Organizational roles',
      organization.data.catalog_counts.organizational_roles,
      Tags,
    ],
  ] as const;
  return (
    <section className="control-section">
      <div className="control-section-heading">
        <div>
          <span className="eyebrow">Organization</span>
          <h2>Organization settings</h2>
          <p>The control plane is scoped to this AJG organization boundary.</p>
        </div>
      </div>
      <section className="surface organization-identity-card">
        <span className="organization-monogram">AJG</span>
        <div>
          <span className="eyebrow">Current organization</span>
          <h3>{organization.data.name}</h3>
          <p>
            Stable tenant key: <code>{organization.data.organization_id}</code>
          </p>
        </div>
      </section>
      <div className="metric-grid organization-metrics">
        {catalogCards.map(([label, value, Icon]) => (
          <div className="metric-card" key={label}>
            <Icon size={20} />
            <strong>{value}</strong>
            <span>Active {label.toLocaleLowerCase()}</span>
          </div>
        ))}
      </div>
      <section className="surface organization-boundary-note">
        <h3>Tenant boundary</h3>
        <p>
          User, policy, access, retrieval, and audit queries derive this
          organization from the authenticated MongoDB profile. This screen
          cannot switch to or address another organization.
        </p>
      </section>
    </section>
  );
}
