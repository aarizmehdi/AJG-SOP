import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, GitCompareArrows, RotateCcw } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import {
  policyListSchema,
  sectionChangesSchema,
  type Policy,
} from '../../types/policy';

export default function PolicyWorkflowPage() {
  const { policyId = '' } = useParams();
  const policies = useQuery({
    queryKey: ['admin-policies'],
    queryFn: () => apiRequest('/admin/policies', policyListSchema),
  });
  if (policies.isLoading) return <RouteSkeleton />;
  const policy = policies.data?.find((item) => item.id === policyId);
  if (!policy)
    return (
      <ErrorState
        title="Policy unavailable"
        detail="The policy is outside your administrative scope or no longer exists."
      />
    );
  return <PolicyWorkflow policy={policy} />;
}

function PolicyWorkflow({ policy }: { policy: Policy }) {
  const versions = [...(policy.versions ?? [])].sort(
    (left, right) => Date.parse(right.created_at) - Date.parse(left.created_at),
  );
  const newest = versions[0];
  const previous = versions[1];
  const comparison = useQuery({
    queryKey: ['version-diff', newest?.id, previous?.id],
    queryFn: () => {
      if (!newest || !previous) return Promise.resolve([]);
      return apiRequest(
        `/admin/versions/${newest.id}/diff?against=${encodeURIComponent(previous.id)}`,
        sectionChangesSchema,
      );
    },
    enabled: Boolean(newest && previous),
  });
  return (
    <section className="admin-content workflow-page">
      <div className="section-heading">
        <div>
          <h2>{policy.title}</h2>
          <p>
            {policy.category} · {policy.policy_number ?? 'No policy number'}
          </p>
        </div>
        <span
          className={`pill ${policy.status === 'active' ? 'pill--active' : 'pill--review'}`}
        >
          {policy.status}
        </span>
      </div>
      <div className="workflow-grid">
        <section className="surface workflow-card">
          <CheckCircle2 />
          <h3>Publication integrity</h3>
          <p>
            The active version changes only after the new derived index is
            staged and verified.
          </p>
        </section>
        <section className="surface workflow-card">
          <GitCompareArrows />
          <h3>Version comparison</h3>
          <p>
            Added, removed, and changed sections include old and new content
            before publication.
          </p>
        </section>
        <section className="surface workflow-card">
          <RotateCcw />
          <h3>Rollback</h3>
          <p>
            Previously verified versions remain available for audited rollback.
          </p>
        </section>
      </div>
      <div className="surface version-list">
        <h3>Version history</h3>
        {policy.versions?.map((version) => (
          <div key={version.id} className="version-row">
            <div>
              <strong>{version.version_label}</strong>
              <span>
                {version.source_document_ids.length} sources · {version.status}
              </span>
            </div>
            <span>
              {version.index_revision ? 'Index verified' : 'Index pending'}
            </span>
          </div>
        ))}
      </div>
      <section
        className="surface version-diff"
        aria-labelledby="version-diff-heading"
      >
        <div className="diff-heading">
          <div>
            <h3 id="version-diff-heading">Version comparison</h3>
            <p>
              {newest && previous
                ? `${previous.version_label} → ${newest.version_label}`
                : 'A second version is required for comparison.'}
            </p>
          </div>
          {comparison.data && <span>{comparison.data.length} changes</span>}
        </div>
        {comparison.isLoading && (
          <div
            className="diff-loading"
            aria-label="Loading version differences"
          >
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        )}
        {comparison.isError && (
          <ErrorState
            title="Comparison unavailable"
            detail="The differences could not be loaded for your administrative scope."
          />
        )}
        {comparison.data?.length === 0 && (
          <p className="diff-empty">
            No canonical section changes were detected.
          </p>
        )}
        {comparison.data?.map((change) => (
          <article
            className={`diff-item diff-item--${change.kind}`}
            key={`${change.kind}-${change.stable_key}`}
          >
            <header>
              <span>{change.kind}</span>
              <strong>{change.heading}</strong>
              {change.access_changed && <small>Access changed</small>}
            </header>
            <div className="diff-columns">
              <div>
                <b>Old</b>
                <pre>{change.old_content ?? '—'}</pre>
              </div>
              <div>
                <b>New</b>
                <pre>{change.new_content ?? '—'}</pre>
              </div>
            </div>
          </article>
        ))}
      </section>
    </section>
  );
}
