import { useQuery } from '@tanstack/react-query';
import { Search, ShieldCheck } from 'lucide-react';
import { useState } from 'react';
import { apiRequest } from '../../../api/client';
import { ErrorState } from '../../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../../components/feedback/RouteSkeleton';
import { auditPageSchema, userPageSchema } from '../../../types/admin';

export default function AuditLogPage() {
  const [action, setAction] = useState('');
  const [entityType, setEntityType] = useState('');
  const [actorId, setActorId] = useState('');
  const [targetUserId, setTargetUserId] = useState('');
  const [occurredFrom, setOccurredFrom] = useState('');
  const [occurredTo, setOccurredTo] = useState('');
  const query = new URLSearchParams();
  if (action) query.set('action', action);
  if (entityType) query.set('entity_type', entityType);
  if (actorId) query.set('actor_id', actorId);
  if (targetUserId) {
    query.set('entity_type', 'employee_profile');
    query.set('entity_id', targetUserId);
  }
  if (occurredFrom)
    query.set(
      'occurred_from',
      new Date(`${occurredFrom}T00:00:00Z`).toISOString(),
    );
  if (occurredTo)
    query.set('occurred_to', new Date(`${occurredTo}T23:59:59Z`).toISOString());
  const users = useQuery({
    queryKey: ['admin-users', 'audit-filters'],
    queryFn: () => apiRequest('/admin/users?limit=100', userPageSchema),
  });
  const events = useQuery({
    queryKey: [
      'admin-audit',
      action,
      entityType,
      actorId,
      targetUserId,
      occurredFrom,
      occurredTo,
    ],
    queryFn: () =>
      apiRequest(
        `/admin/audit-events${query.size ? `?${query.toString()}` : ''}`,
        auditPageSchema,
      ),
  });
  if (events.isPending) return <RouteSkeleton label="Loading audit history" />;
  if (events.isError)
    return (
      <ErrorState
        title="Audit log unavailable"
        detail="Organization-wide audit history requires System Administrator access."
      />
    );
  return (
    <section className="control-section">
      <div className="control-section-heading">
        <div>
          <span className="eyebrow">Governance</span>
          <h2>Audit log</h2>
          <p>
            Read-only history of security, identity, organization, and policy
            actions.
          </p>
        </div>
      </div>
      <div className="surface user-toolbar audit-toolbar">
        <label className="admin-search">
          <Search size={17} />
          <input
            aria-label="Filter by exact action"
            placeholder="Filter exact action"
            value={action}
            onChange={(event) => {
              setAction(event.target.value);
            }}
          />
        </label>
        <select
          aria-label="Filter by entity type"
          value={entityType}
          onChange={(event) => {
            setEntityType(event.target.value);
          }}
        >
          <option value="">All entity types</option>
          <option value="employee_profile">User</option>
          <option value="department">Department</option>
          <option value="location">Location</option>
          <option value="organizational_role">Organizational role</option>
          <option value="policy">Policy</option>
        </select>
        <select
          aria-label="Filter by actor"
          value={actorId}
          onChange={(event) => {
            setActorId(event.target.value);
          }}
        >
          <option value="">All actors</option>
          {users.data?.items.map((user) => (
            <option value={user.id} key={user.id}>
              {user.display_name}
            </option>
          ))}
        </select>
        <select
          aria-label="Filter by affected user"
          value={targetUserId}
          onChange={(event) => {
            setTargetUserId(event.target.value);
          }}
        >
          <option value="">All affected users</option>
          {users.data?.items.map((user) => (
            <option value={user.id} key={user.id}>
              {user.display_name}
            </option>
          ))}
        </select>
        <label className="audit-date-filter">
          From
          <input
            type="date"
            value={occurredFrom}
            onChange={(event) => {
              setOccurredFrom(event.target.value);
            }}
          />
        </label>
        <label className="audit-date-filter">
          To
          <input
            type="date"
            value={occurredTo}
            onChange={(event) => {
              setOccurredTo(event.target.value);
            }}
          />
        </label>
      </div>
      {!events.data.items.length ? (
        <div className="surface control-empty">
          <ShieldCheck />
          <h3>No matching activity</h3>
          <p>
            Administrative mutations will appear here without sensitive
            credentials.
          </p>
        </div>
      ) : (
        <div className="surface audit-list">
          <div className="audit-list-head">
            <span>When</span>
            <span>Actor</span>
            <span>Action</span>
            <span>Target</span>
          </div>
          {events.data.items.map((event) => (
            <div className="audit-list-row" key={event.id}>
              <time dateTime={event.occurred_at}>
                {new Intl.DateTimeFormat(undefined, {
                  dateStyle: 'medium',
                  timeStyle: 'short',
                }).format(new Date(event.occurred_at))}
              </time>
              <code>{event.actor_id}</code>
              <strong>{event.action.replaceAll('_', ' ')}</strong>
              <span>
                {event.entity_type} · {event.entity_id}
              </span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
