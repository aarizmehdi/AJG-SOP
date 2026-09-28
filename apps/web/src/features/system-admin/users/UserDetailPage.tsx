import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  CheckCircle2,
  KeyRound,
  ShieldOff,
  ShieldCheck,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiRequest } from '../../../api/client';
import { ErrorState } from '../../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../../components/feedback/RouteSkeleton';
import {
  adminUserSchema,
  auditPageSchema,
  resetLinkSchema,
} from '../../../types/admin';
import { profileSchema } from '../../../types/profile';
import { UserAccessEditor } from './UserAccessEditor';
import { formIsComplete, userToForm, type UserFormState } from './userForm';
import { systemAdminErrorDetail } from '../errorDetail';

export default function UserDetailPage() {
  const { userId = '' } = useParams();
  const queryClient = useQueryClient();
  const [formOverride, setForm] = useState<UserFormState | null>(null);
  const [showDisable, setShowDisable] = useState(false);
  const [confirmSelfRoleChange, setConfirmSelfRoleChange] = useState(false);
  const [confirmationEmail, setConfirmationEmail] = useState('');
  const [resetLink, setResetLink] = useState<string | null>(null);
  const currentProfile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });
  const user = useQuery({
    queryKey: ['admin-user', userId],
    queryFn: () => apiRequest(`/admin/users/${userId}`, adminUserSchema),
  });
  const activity = useQuery({
    queryKey: ['admin-user-activity', userId],
    queryFn: () =>
      apiRequest(
        `/admin/audit-events?entity_type=employee_profile&entity_id=${encodeURIComponent(userId)}&limit=20`,
        auditPageSchema,
      ),
  });
  const form = formOverride ?? (user.data ? userToForm(user.data) : null);
  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ['admin-user', userId] });
    await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
    await queryClient.invalidateQueries({
      queryKey: ['system-admin-overview'],
    });
  };
  const save = useMutation({
    mutationFn: () => {
      if (!form || !user.data) throw new Error('User is unavailable');
      return apiRequest(`/admin/users/${userId}`, adminUserSchema, {
        method: 'PATCH',
        body: JSON.stringify({
          ...form,
          expected_version: user.data.version,
          confirm_self_role_change: confirmSelfRoleChange,
        }),
      });
    },
    onSuccess: async (updated) => {
      setForm(userToForm(updated));
      await refresh();
    },
  });
  const disable = useMutation({
    mutationFn: () =>
      apiRequest(`/admin/users/${userId}/disable`, adminUserSchema, {
        method: 'POST',
        body: JSON.stringify({ confirmation_email: confirmationEmail }),
      }),
    onSuccess: async () => {
      setShowDisable(false);
      await refresh();
    },
  });
  const reactivate = useMutation({
    mutationFn: () =>
      apiRequest(`/admin/users/${userId}/reactivate`, adminUserSchema, {
        method: 'POST',
      }),
    onSuccess: refresh,
  });
  const reset = useMutation({
    mutationFn: () =>
      apiRequest(`/admin/users/${userId}/password-reset`, resetLinkSchema, {
        method: 'POST',
      }),
    onSuccess: (result) => {
      setResetLink(result.reset_link);
    },
  });
  if (user.isPending || currentProfile.isPending)
    return <RouteSkeleton label="Loading user" />;
  if (user.isError)
    return (
      <ErrorState
        title="User unavailable"
        detail={systemAdminErrorDetail(
          user.error,
          'This user does not exist in your organization.',
        )}
      />
    );
  if (!form) return <RouteSkeleton label="Preparing user access" />;
  const isSelf = currentProfile.data?.id === user.data.id;
  const removesOwnSystemAdmin =
    isSelf &&
    user.data.application_roles.includes('system_admin') &&
    !form.application_roles.includes('system_admin');
  return (
    <section className="control-section">
      <div className="control-section-heading user-detail-heading">
        <div>
          <Link className="back-link" to="/admin/users">
            <ArrowLeft size={16} /> Users
          </Link>
          <div className="user-title-line">
            <span className="user-avatar">
              {user.data.display_name.slice(0, 1).toLocaleUpperCase()}
            </span>
            <div>
              <h2>{user.data.display_name}</h2>
              <p>
                {user.data.email} ·{' '}
                {user.data.identity_linked
                  ? 'Firebase identity linked'
                  : 'Identity link unavailable'}
              </p>
            </div>
          </div>
        </div>
        <span className={`status-text ${user.data.status}`}>
          {user.data.status.replace('_', ' ')}
        </span>
      </div>
      <UserAccessEditor value={form} onChange={setForm} />
      {save.isError && (
        <p className="form-error form-error-panel">{save.error.message}</p>
      )}
      {removesOwnSystemAdmin && (
        <label className="self-role-confirmation surface">
          <input
            type="checkbox"
            checked={confirmSelfRoleChange}
            onChange={(event) => {
              setConfirmSelfRoleChange(event.target.checked);
            }}
          />
          <span>
            <strong>Confirm removal of my System Administrator access</strong>
            <small>
              The server will still block this change if you are the last active
              System Administrator.
            </small>
          </span>
        </label>
      )}
      <section className="surface security-actions">
        <div>
          <h3>Security actions</h3>
          <p>
            Password reset links are generated by Firebase and are never stored.
          </p>
        </div>
        <div className="security-action-buttons">
          <button
            className="button button--secondary"
            type="button"
            disabled={reset.isPending}
            onClick={() => {
              reset.mutate();
            }}
          >
            <KeyRound size={16} /> Generate password reset
          </button>
          {user.data.active ? (
            <button
              className="button button--danger-quiet"
              type="button"
              onClick={() => {
                setShowDisable(true);
              }}
            >
              <ShieldOff size={16} /> Disable user
            </button>
          ) : (
            <button
              className="button button--secondary"
              type="button"
              disabled={reactivate.isPending}
              onClick={() => {
                reactivate.mutate();
              }}
            >
              <ShieldCheck size={16} />{' '}
              {reactivate.isPending ? 'Reactivating…' : 'Reactivate'}
            </button>
          )}
        </div>
        {(reset.isError || reactivate.isError) && (
          <p className="form-error">
            {(reset.error ?? reactivate.error)?.message}
          </p>
        )}
        {resetLink && (
          <div className="activation-link">
            <span>{resetLink}</span>
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard.writeText(resetLink);
              }}
            >
              Copy private link
            </button>
          </div>
        )}
      </section>
      <section className="surface user-activity-panel">
        <div>
          <h3>Activity</h3>
          <p>Security and access changes recorded for this user.</p>
        </div>
        {activity.isPending ? (
          <p role="status">Loading user activity…</p>
        ) : activity.isError || !activity.data.items.length ? (
          <p className="empty-copy">No user-specific activity is available.</p>
        ) : (
          <div className="activity-list">
            {activity.data.items.map((event) => (
              <div className="activity-row" key={event.id}>
                <span className="activity-marker" />
                <div>
                  <strong>{event.action.replaceAll('_', ' ')}</strong>
                  <small>Actor: {event.actor_id}</small>
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
      <div className="sticky-form-actions">
        <span className="save-context">
          <CheckCircle2 size={16} /> Version {user.data.version}
        </span>
        <button
          className="button button--primary"
          type="button"
          disabled={
            !formIsComplete(form) ||
            save.isPending ||
            (removesOwnSystemAdmin && !confirmSelfRoleChange)
          }
          onClick={() => {
            save.mutate();
          }}
        >
          {save.isPending ? 'Saving…' : 'Save access changes'}
        </button>
      </div>
      {showDisable && (
        <div className="admin-overlay" role="presentation">
          <section
            className="confirmation-card"
            role="alertdialog"
            aria-modal="true"
          >
            <h3>Disable {user.data.display_name}?</h3>
            <p>
              This immediately disables Firebase sign-in and AJG membership.
              Audit and policy history remain.
            </p>
            {isSelf && (
              <label>
                Enter your email to confirm
                <input
                  value={confirmationEmail}
                  onChange={(event) => {
                    setConfirmationEmail(event.target.value);
                  }}
                />
              </label>
            )}
            {disable.isError && (
              <p className="form-error">{disable.error.message}</p>
            )}
            <div className="form-actions">
              <button
                className="button button--secondary"
                type="button"
                onClick={() => {
                  setShowDisable(false);
                }}
              >
                Cancel
              </button>
              <button
                className="button button--danger"
                type="button"
                disabled={
                  disable.isPending ||
                  (isSelf && confirmationEmail !== user.data.email)
                }
                onClick={() => {
                  disable.mutate();
                }}
              >
                {disable.isPending ? 'Disabling…' : 'Disable user'}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
