import { useQuery } from '@tanstack/react-query';
import { CheckCircle2, SearchCheck, XCircle } from 'lucide-react';
import { useState } from 'react';
import { apiRequest } from '../../../api/client';
import { ErrorState } from '../../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../../components/feedback/RouteSkeleton';
import { accessInspectionSchema, userPageSchema } from '../../../types/admin';
import { policyListSchema } from '../../../types/policy';
import { systemAdminErrorDetail } from '../errorDetail';

export default function AccessInspectorPage() {
  const [userId, setUserId] = useState('');
  const [policyId, setPolicyId] = useState('');
  const users = useQuery({
    queryKey: ['admin-users', 'access-inspector'],
    queryFn: () => apiRequest('/admin/users?limit=100', userPageSchema),
  });
  const policies = useQuery({
    queryKey: ['admin-policies'],
    queryFn: () => apiRequest('/admin/policies', policyListSchema),
  });
  const inspection = useQuery({
    queryKey: ['access-inspection', userId, policyId],
    queryFn: () =>
      apiRequest(
        `/admin/access/users/${encodeURIComponent(userId)}/policies/${encodeURIComponent(policyId)}`,
        accessInspectionSchema,
      ),
    enabled: Boolean(userId && policyId),
  });
  if (users.isPending || policies.isPending)
    return <RouteSkeleton label="Loading access inspector" />;
  if (users.isError || policies.isError)
    return (
      <ErrorState
        title="Access inspector unavailable"
        detail={systemAdminErrorDetail(users.error ?? policies.error)}
      />
    );
  return (
    <section className="control-section">
      <div className="control-section-heading">
        <div>
          <span className="eyebrow">Governance</span>
          <h2>Access overview</h2>
          <p>Explain why an employee can or cannot access a published SOP.</p>
        </div>
      </div>
      <section className="surface inspector-controls">
        <label>
          Employee
          <select
            value={userId}
            onChange={(event) => {
              setUserId(event.target.value);
            }}
          >
            <option value="">Choose an employee</option>
            {users.data.items.map((user) => (
              <option value={user.id} key={user.id}>
                {user.display_name} · {user.email}
              </option>
            ))}
          </select>
        </label>
        <label>
          Published SOP
          <select
            value={policyId}
            onChange={(event) => {
              setPolicyId(event.target.value);
            }}
          >
            <option value="">Choose a policy</option>
            {policies.data
              .filter((policy) => policy.active_version_id)
              .map((policy) => (
                <option value={policy.id} key={policy.id}>
                  {policy.title}
                </option>
              ))}
          </select>
        </label>
      </section>
      {!userId || !policyId ? (
        <div className="surface control-empty compact">
          <SearchCheck />
          <h3>Select a user and policy</h3>
          <p>
            The inspector evaluates the same three dimensions used by backend
            authorization.
          </p>
        </div>
      ) : inspection.isPending ? (
        <RouteSkeleton label="Evaluating access" />
      ) : inspection.isError ? (
        <ErrorState
          title="Access could not be evaluated"
          detail={systemAdminErrorDetail(inspection.error)}
        />
      ) : (
        <section
          className={`surface access-result ${inspection.data.authorized ? 'authorized' : 'denied'}`}
        >
          <header>
            {inspection.data.authorized ? <CheckCircle2 /> : <XCircle />}
            <div>
              <span>{inspection.data.user.display_name}</span>
              <h3>
                {inspection.data.authorized ? 'AUTHORIZED' : 'NOT AUTHORIZED'}
              </h3>
              <p>{inspection.data.policy.title}</p>
            </div>
          </header>
          <div className="access-dimension-list">
            {Object.entries(inspection.data.dimensions).map(([name, check]) => (
              <div className="access-dimension" key={name}>
                <div>
                  <strong>{name.replace('_', ' ')}</strong>
                  <span>{check.allowed ? 'Match' : 'No match'}</span>
                </div>
                <dl>
                  <div>
                    <dt>Employee</dt>
                    <dd>{check.user_values.join(', ') || 'None'}</dd>
                  </div>
                  <div>
                    <dt>Policy</dt>
                    <dd>
                      {check.policy_mode === 'all'
                        ? 'All'
                        : check.policy_values.join(', ')}
                    </dd>
                  </div>
                </dl>
              </div>
            ))}
          </div>
        </section>
      )}
    </section>
  );
}
