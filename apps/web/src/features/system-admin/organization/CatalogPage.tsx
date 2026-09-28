import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Archive, Pencil, Plus, RotateCcw, X } from 'lucide-react';
import { useState } from 'react';
import { apiRequest } from '../../../api/client';
import { ErrorState } from '../../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../../components/feedback/RouteSkeleton';
import {
  catalogItemSchema,
  catalogListSchema,
  type CatalogItem,
  type CatalogKind,
} from '../../../types/admin';
import { systemAdminErrorDetail } from '../errorDetail';

const copy: Record<
  CatalogKind,
  { title: string; singular: string; description: string }
> = {
  departments: {
    title: 'Departments',
    singular: 'department',
    description: 'Business departments used by employee and SOP access rules.',
  },
  locations: {
    title: 'Locations',
    singular: 'location',
    description:
      'Organization sites and operating locations used in access rules.',
  },
  organizational_roles: {
    title: 'Organizational roles',
    singular: 'organizational role',
    description:
      'Job roles such as Store Keeper. These are separate from application roles.',
  },
};

export function CatalogPage({ kind }: { kind: CatalogKind }) {
  const queryClient = useQueryClient();
  const [editor, setEditor] = useState<CatalogItem | 'new' | null>(null);
  const [name, setName] = useState('');
  const [key, setKey] = useState('');
  const [description, setDescription] = useState('');
  const [confirming, setConfirming] = useState<CatalogItem | null>(null);
  const list = useQuery({
    queryKey: ['catalog', kind],
    queryFn: () => apiRequest(`/admin/${kind}`, catalogListSchema),
  });
  const save = useMutation({
    mutationFn: () => {
      if (editor === 'new') {
        return apiRequest(`/admin/${kind}`, catalogItemSchema, {
          method: 'POST',
          body: JSON.stringify({ key, name, description: description || null }),
        });
      }
      if (!editor) throw new Error('Choose a catalog item');
      return apiRequest(`/admin/${kind}/${editor.id}`, catalogItemSchema, {
        method: 'PATCH',
        body: JSON.stringify({
          name,
          description: description || null,
          expected_version: editor.version,
        }),
      });
    },
    onSuccess: async () => {
      setEditor(null);
      await queryClient.invalidateQueries({ queryKey: ['catalog', kind] });
      await queryClient.invalidateQueries({
        queryKey: ['organization-catalogs'],
      });
      await queryClient.invalidateQueries({
        queryKey: ['system-admin-overview'],
      });
    },
  });
  const lifecycle = useMutation({
    mutationFn: (item: CatalogItem) =>
      apiRequest(`/admin/${kind}/${item.id}`, catalogItemSchema, {
        method: 'PATCH',
        body: JSON.stringify({
          active: !item.active,
          expected_version: item.version,
        }),
      }),
    onSuccess: async () => {
      setConfirming(null);
      await queryClient.invalidateQueries({ queryKey: ['catalog', kind] });
      await queryClient.invalidateQueries({
        queryKey: ['organization-catalogs'],
      });
    },
  });
  const openEditor = (item: CatalogItem | 'new') => {
    setEditor(item);
    setName(item === 'new' ? '' : item.name);
    setKey(item === 'new' ? '' : item.key);
    setDescription(item === 'new' ? '' : (item.description ?? ''));
    save.reset();
  };
  if (list.isPending)
    return <RouteSkeleton label={`Loading ${copy[kind].title}`} />;
  if (list.isError)
    return (
      <ErrorState
        title={`${copy[kind].title} unavailable`}
        detail={systemAdminErrorDetail(list.error)}
      />
    );
  return (
    <section className="control-section">
      <div className="control-section-heading">
        <div>
          <span className="eyebrow">Organization structure</span>
          <h2>{copy[kind].title}</h2>
          <p>{copy[kind].description}</p>
        </div>
        <button
          className="button button--primary"
          type="button"
          onClick={() => {
            openEditor('new');
          }}
        >
          <Plus size={17} /> Add {copy[kind].singular}
        </button>
      </div>
      {!list.data.length ? (
        <div className="surface control-empty">
          <h3>No {copy[kind].title.toLocaleLowerCase()} configured</h3>
          <p>Create the first authoritative option before assigning access.</p>
        </div>
      ) : (
        <div className="surface catalog-table" role="table">
          <div className="catalog-table-head" role="row">
            <span>Name</span>
            <span>Stable key</span>
            <span>Usage</span>
            <span>Status</span>
            <span className="sr-only">Actions</span>
          </div>
          {list.data.map((item) => (
            <div className="catalog-table-row" role="row" key={item.id}>
              <div>
                <strong>{item.name}</strong>
                <small>{item.description ?? 'No description'}</small>
              </div>
              <code>{item.key}</code>
              <span>{item.usage?.total ?? 0} references</span>
              <span
                className={`status-text ${item.active ? 'active' : 'inactive'}`}
              >
                {item.active ? 'Active' : 'Inactive'}
              </span>
              <div className="row-actions">
                <button
                  type="button"
                  title={`Edit ${item.name}`}
                  onClick={() => {
                    openEditor(item);
                  }}
                >
                  <Pencil size={16} />
                </button>
                <button
                  type="button"
                  title={
                    item.active
                      ? `Deactivate ${item.name}`
                      : `Reactivate ${item.name}`
                  }
                  onClick={() => {
                    setConfirming(item);
                  }}
                >
                  {item.active ? (
                    <Archive size={16} />
                  ) : (
                    <RotateCcw size={16} />
                  )}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      {editor && (
        <div className="admin-overlay" role="presentation">
          <section className="admin-drawer" role="dialog" aria-modal="true">
            <div className="panel-heading">
              <div>
                <span className="eyebrow">
                  {editor === 'new' ? 'Create' : 'Edit'}
                </span>
                <h3>{copy[kind].singular}</h3>
              </div>
              <button
                className="icon-button"
                type="button"
                aria-label="Close editor"
                onClick={() => {
                  setEditor(null);
                }}
              >
                <X />
              </button>
            </div>
            <label>
              Display name
              <input
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                }}
              />
            </label>
            <label>
              Stable key
              <input
                value={key}
                disabled={editor !== 'new'}
                onChange={(event) => {
                  setKey(event.target.value);
                }}
              />
              <small>
                {editor === 'new'
                  ? 'Lowercase letters, numbers, and hyphens. It cannot be changed later.'
                  : 'Keys remain unchanged when a display name is renamed.'}
              </small>
            </label>
            <label>
              Description
              <textarea
                rows={4}
                value={description}
                onChange={(event) => {
                  setDescription(event.target.value);
                }}
              />
            </label>
            {save.isError && <p className="form-error">{save.error.message}</p>}
            <div className="form-actions">
              <button
                className="button button--secondary"
                type="button"
                onClick={() => {
                  setEditor(null);
                }}
              >
                Cancel
              </button>
              <button
                className="button button--primary"
                type="button"
                disabled={!name.trim() || !key.trim() || save.isPending}
                onClick={() => {
                  save.mutate();
                }}
              >
                {save.isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
          </section>
        </div>
      )}
      {confirming && (
        <div className="admin-overlay" role="presentation">
          <section
            className="confirmation-card"
            role="alertdialog"
            aria-modal="true"
          >
            <h3>
              {confirming.active ? 'Deactivate' : 'Reactivate'}{' '}
              {confirming.name}?
            </h3>
            {confirming.active ? (
              <p>
                Used by {confirming.usage?.active_users ?? 0} active users,{' '}
                {confirming.usage?.policies ?? 0} policies, and{' '}
                {confirming.usage?.sop_administrators ?? 0} SOP administrators.
                Referenced items are blocked from deactivation.
              </p>
            ) : (
              <p>This option will become available for new assignments.</p>
            )}
            {lifecycle.isError && (
              <p className="form-error">{lifecycle.error.message}</p>
            )}
            <div className="form-actions">
              <button
                className="button button--secondary"
                type="button"
                onClick={() => {
                  setConfirming(null);
                }}
              >
                Cancel
              </button>
              <button
                className="button button--primary"
                type="button"
                disabled={lifecycle.isPending}
                onClick={() => {
                  lifecycle.mutate(confirming);
                }}
              >
                {lifecycle.isPending ? 'Updating…' : 'Confirm'}
              </button>
            </div>
          </section>
        </div>
      )}
    </section>
  );
}
