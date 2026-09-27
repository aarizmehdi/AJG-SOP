import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, CheckCircle2, Copy, ExternalLink } from 'lucide-react';
import { useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiRequest } from '../../../api/client';
import { createdUserSchema } from '../../../types/admin';
import { UserAccessEditor } from './UserAccessEditor';
import { emptyUserForm, formIsComplete } from './userForm';

export default function CreateUserPage() {
  const [form, setForm] = useState(emptyUserForm);
  const [copied, setCopied] = useState(false);
  const idempotencyKey = useRef(crypto.randomUUID());
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const create = useMutation({
    mutationFn: () =>
      apiRequest('/admin/users', createdUserSchema, {
        method: 'POST',
        headers: { 'Idempotency-Key': idempotencyKey.current },
        body: JSON.stringify(form),
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['admin-users'] });
      await queryClient.invalidateQueries({
        queryKey: ['system-admin-overview'],
      });
    },
  });
  if (create.data) {
    return (
      <section className="control-section activation-result">
        <div className="surface activation-card">
          <CheckCircle2 aria-hidden="true" />
          <span className="eyebrow">Account created</span>
          <h2>{create.data.user.display_name}</h2>
          <p>
            Firebase identity and AJG organization membership were created.
            Share this one-time password setup link through an approved private
            channel.
          </p>
          <div className="activation-link">
            <span>{create.data.activation_link}</span>
            <button
              type="button"
              onClick={() => {
                void navigator.clipboard.writeText(create.data.activation_link);
                setCopied(true);
              }}
            >
              <Copy size={16} /> {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
          <small>
            The link is not written to application logs or audit metadata.
          </small>
          <div className="form-actions">
            <button
              className="button button--secondary"
              type="button"
              onClick={() => {
                idempotencyKey.current = crypto.randomUUID();
                setForm(emptyUserForm);
                create.reset();
              }}
            >
              Create another user
            </button>
            <button
              className="button button--primary"
              type="button"
              onClick={() => {
                void navigate(`/admin/users/${create.data.user.id}`);
              }}
            >
              Open user <ExternalLink size={16} />
            </button>
          </div>
        </div>
      </section>
    );
  }
  return (
    <section className="control-section">
      <div className="control-section-heading">
        <div>
          <Link className="back-link" to="/admin/users">
            <ArrowLeft size={16} /> Users
          </Link>
          <h2>Create user</h2>
          <p>
            Create a Firebase identity and tenant-scoped AJG membership
            together.
          </p>
        </div>
      </div>
      <UserAccessEditor value={form} onChange={setForm} />
      {create.isError && (
        <p className="form-error form-error-panel">{create.error.message}</p>
      )}
      <div className="sticky-form-actions">
        <Link className="button button--secondary" to="/admin/users">
          Cancel
        </Link>
        <button
          className="button button--primary"
          type="button"
          disabled={!formIsComplete(form) || create.isPending}
          onClick={() => {
            create.mutate();
          }}
        >
          {create.isPending ? 'Creating secure account…' : 'Create user'}
        </button>
      </div>
    </section>
  );
}
