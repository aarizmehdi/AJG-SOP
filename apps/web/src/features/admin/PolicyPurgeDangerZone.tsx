import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Trash2 } from 'lucide-react';
import { apiRequest } from '../../api/client';
import { purgePreviewSchema, purgeResultSchema } from '../../types/purge';
import { useLanguage } from '../language/useLanguage';
import { purgeCopy } from './purgeCopy';

export function PolicyPurgeDangerZone({ policyId }: { policyId: string }) {
  const { language } = useLanguage();
  const copy = purgeCopy[language];
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [title, setTitle] = useState('');
  const [phrase, setPhrase] = useState('');
  const preview = useMutation({
    mutationFn: () =>
      apiRequest(
        `/admin/policies/${encodeURIComponent(policyId)}/purge-preview`,
        purgePreviewSchema,
      ),
    onSuccess: () => {
      setTitle('');
      setPhrase('');
      purge.reset();
    },
  });
  const purge = useMutation({
    mutationFn: () =>
      apiRequest(
        `/admin/policies/${encodeURIComponent(policyId)}/purge`,
        purgeResultSchema,
        {
          method: 'POST',
          body: JSON.stringify({
            title,
            phrase,
            preview_token: preview.data?.preview_token,
          }),
        },
      ),
    onSuccess: (result) => {
      if (
        result.status === 'complete' ||
        result.status === 'already_complete'
      ) {
        queryClient.clear();
        void navigate('/admin/policies', {
          replace: true,
          state: { purged: true },
        });
      }
    },
  });
  const busy = preview.isPending || purge.isPending;
  return (
    <section className="policy-danger-zone" aria-label={copy.heading}>
      <h3>{copy.heading}</h3>
      <p>{copy.explain}</p>
      <button
        className="button purge-button"
        type="button"
        disabled={busy}
        onClick={() => {
          preview.mutate();
        }}
      >
        <Trash2 size={16} />
        {preview.isPending ? copy.previewing : copy.action}
      </button>
      {preview.isPending && (
        <div className="purge-skeleton" aria-label={copy.previewing}>
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      )}
      {(preview.isError || purge.isError) && (
        <p role="alert">{(preview.error ?? purge.error)?.message}</p>
      )}
      {preview.data && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            if (
              !busy &&
              title === preview.data.title &&
              phrase === 'DELETE PERMANENTLY'
            )
              purge.mutate();
          }}
        >
          <h4>{preview.data.title}</h4>
          <p className="purge-policy-id">{preview.data.policy_id}</p>
          <dl className="purge-inventory">
            <div>
              <dt>{copy.published}</dt>
              <dd>{preview.data.published ? copy.yes : copy.no}</dd>
            </div>
            {Object.entries(copy.resources).map(([key, label]) => (
              <div key={key}>
                <dt>{label}</dt>
                <dd>{preview.data.counts.mongo[key] ?? 0}</dd>
              </div>
            ))}
            <div>
              <dt>{copy.other}</dt>
              <dd>
                {Object.entries(preview.data.counts.mongo)
                  .filter(([key]) => !Object.hasOwn(copy.resources, key))
                  .reduce((sum, [, n]) => sum + n, 0)}
              </dd>
            </div>
            <div>
              <dt>{copy.objects}</dt>
              <dd>{preview.data.counts.r2_objects}</dd>
            </div>
            <div>
              <dt>{copy.bytes}</dt>
              <dd>{preview.data.counts.r2_bytes.toLocaleString()}</dd>
            </div>
            <div>
              <dt>{copy.vectors}</dt>
              <dd>{preview.data.counts.pinecone_vectors}</dd>
            </div>
          </dl>
          <p role="note">{copy.warning}</p>
          <p className="purge-limit">{copy.history}</p>
          <label>
            {copy.typeTitle}
            <input
              value={title}
              disabled={purge.isPending}
              autoComplete="off"
              onChange={(e) => {
                setTitle(e.target.value);
              }}
            />
          </label>
          <label>
            {copy.typePhrase}
            <input
              value={phrase}
              disabled={purge.isPending}
              autoComplete="off"
              dir="ltr"
              onChange={(e) => {
                setPhrase(e.target.value);
              }}
            />
          </label>
          {purge.data?.status === 'failed' && (
            <p role="alert">
              {copy.failed}{' '}
              {Object.entries(purge.data.stages)
                .map(([stage, status]) => `${stage}: ${status}`)
                .join(' · ')}
            </p>
          )}
          <div className="purge-actions">
            <button
              className="button purge-button"
              disabled={
                busy ||
                title !== preview.data.title ||
                phrase !== 'DELETE PERMANENTLY'
              }
              type="submit"
            >
              {purge.isPending ? copy.deleting : copy.confirm}
            </button>
            <button
              className="button"
              type="button"
              disabled={busy}
              onClick={() => {
                preview.reset();
                purge.reset();
                setTitle('');
                setPhrase('');
              }}
            >
              {copy.cancel}
            </button>
          </div>
        </form>
      )}
    </section>
  );
}
