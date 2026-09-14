import { ArrowRight, FileText } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiRequest } from '../../api/client';
import { EmptyState } from '../../components/feedback/StatePanel';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { Button } from '../../components/ui/Button';
import { policyListSchema } from '../../types/policy';

export default function AdminLibraryPage() {
  const policies = useQuery({
    queryKey: ['admin-policies'],
    queryFn: () => apiRequest('/admin/policies', policyListSchema),
  });
  if (policies.isLoading) return <RouteSkeleton />;
  if (policies.isError)
    return (
      <ErrorState
        title="Policy library unavailable"
        detail="Check the API connection and your administrative scope."
      />
    );
  return (
    <section className="admin-content">
      <div className="library-toolbar">
        <div>
          <h2>Policies</h2>
          <p>Published and in-progress SOP versions.</p>
        </div>
        <Link to="/admin/add">
          <Button>+ Add SOP</Button>
        </Link>
      </div>
      <div className="policy-list surface">
        <div className="policy-row policy-row--header">
          <span>Policy</span>
          <span>Audience</span>
          <span>Status</span>
          <span>Updated</span>
          <span />
        </div>
        {policies.data?.map((policy) => (
          <div className="policy-row" key={policy.id}>
            <span className="policy-title">
              <span className="file-icon">
                <FileText />
              </span>
              <span>
                <strong>{policy.title}</strong>
                <small>
                  {policy.category}
                  {policy.title.startsWith('SYNTHETIC')
                    ? ' · Fixture data'
                    : ''}
                </small>
              </span>
            </span>
            <span>
              {policy.versions?.[0]?.access.departments.mode === 'all'
                ? 'All departments'
                : policy.versions?.[0]?.access.departments.values.join(', ')}
            </span>
            <span>
              <span
                className={`pill ${policy.status === 'active' ? 'pill--active' : 'pill--review'}`}
              >
                {policy.status}
              </span>
            </span>
            <span>{new Date(policy.updated_at).toLocaleDateString()}</span>
            <Link
              to={`/admin/policies/${policy.id}`}
              aria-label={`Open ${policy.title}`}
            >
              <ArrowRight />
            </Link>
          </div>
        ))}
      </div>
      {!policies.data?.length && (
        <EmptyState
          title="No policies yet"
          detail="Add the first SOP source to start a reviewable policy version."
        />
      )}
    </section>
  );
}
