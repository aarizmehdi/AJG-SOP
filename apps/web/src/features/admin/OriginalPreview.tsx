import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { FileWarning, Upload } from 'lucide-react';
import { useState } from 'react';
import { z } from 'zod';
import { apiRequest } from '../../api/client';
import { useAdminCopy } from './adminCopy';

const previewSchema = z.discriminatedUnion('kind', [
  z.object({ kind: z.literal('missing_pdf') }),
  z.object({ kind: z.literal('other') }),
  z.object({
    kind: z.literal('pdf'),
    url: z.url(),
    file_name: z.string(),
    media_type: z.literal('application/pdf'),
    legacy_repair_required: z.boolean(),
    expires_in_seconds: z.number(),
  }),
  z.object({
    kind: z.literal('image'),
    url: z.url(),
    file_name: z.string(),
    media_type: z.string(),
    legacy_repair_required: z.boolean(),
    expires_in_seconds: z.number(),
  }),
]);

export function OriginalPreview({
  sourceId,
  canAttach = false,
}: {
  sourceId: string;
  canAttach?: boolean;
}) {
  const { copy } = useAdminCopy();
  const queryClient = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const preview = useQuery({
    queryKey: ['source-original-preview', sourceId],
    queryFn: () =>
      apiRequest(`/admin/sources/${sourceId}/original/preview`, previewSchema, {
        signal: AbortSignal.timeout(15_000),
      }),
    retry: false,
    staleTime: 90_000,
  });
  const attach = useMutation({
    mutationFn: () => {
      if (!file) throw new Error('Choose an original PDF');
      const body = new FormData();
      body.set('file', file);
      return apiRequest(
        `/admin/sources/${sourceId}/attach-original`,
        z.object({ id: z.string() }).loose(),
        { method: 'POST', body },
      );
    },
    onSuccess: async () => {
      setFile(null);
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ['source-original-preview', sourceId],
        }),
        queryClient.invalidateQueries({
          queryKey: ['source-review', sourceId],
        }),
        queryClient.invalidateQueries({ queryKey: ['admin-policy-viewer'] }),
        queryClient.invalidateQueries({ queryKey: ['admin-policies'] }),
      ]);
    },
  });

  if (preview.isPending)
    return (
      <div className="source-preview" role="status">
        {copy.originalLoading}
      </div>
    );
  if (preview.isError)
    return (
      <div className="source-preview" role="alert">
        <FileWarning aria-hidden="true" />
        <strong>{copy.originalUnavailable}</strong>
        <p>{preview.error.message}</p>
        <button type="button" onClick={() => void preview.refetch()}>
          {copy.tryAgain}
        </button>
      </div>
    );
  if (preview.data.kind === 'missing_pdf')
    return (
      <div className="source-preview" role="status">
        <FileWarning aria-hidden="true" />
        <strong>{copy.noOriginalPdf}</strong>
        {canAttach && (
          <div className="attach-original">
            <label>
              {copy.attachOriginalPdf}
              <input
                type="file"
                accept=".pdf,application/pdf"
                onChange={(event) => {
                  setFile(event.target.files?.[0] ?? null);
                }}
              />
            </label>
            <button
              type="button"
              className="button button--secondary"
              disabled={!file || attach.isPending}
              onClick={() => {
                attach.mutate();
              }}
            >
              <Upload size={16} aria-hidden="true" />
              {attach.isPending
                ? copy.attachingOriginal
                : copy.attachOriginalPdf}
            </button>
            {attach.isError && <p role="alert">{attach.error.message}</p>}
          </div>
        )}
      </div>
    );
  if (preview.data.kind === 'other')
    return (
      <div className="source-preview" role="status">
        {copy.previewOther}
      </div>
    );
  return (
    <div className="source-preview source-preview--document">
      <div className="original-preview-heading">
        <strong>
          {preview.data.kind === 'pdf' ? copy.originalPdf : copy.originalImage}:{' '}
          {preview.data.file_name}
        </strong>
        <a
          href={preview.data.url}
          target="_blank"
          rel="noopener noreferrer"
          referrerPolicy="no-referrer"
        >
          {copy.openOriginal}
        </a>
      </div>
      {preview.data.legacy_repair_required && (
        <p className="reader-notice" role="status">
          {copy.legacySourceRepair}
        </p>
      )}
      {preview.data.kind === 'pdf' ? (
        <iframe
          className="source-object"
          src={preview.data.url}
          title={`${copy.originalPdf}: ${preview.data.file_name}`}
          referrerPolicy="no-referrer"
        />
      ) : (
        <img
          className="source-image"
          src={preview.data.url}
          alt={`${copy.originalImage}: ${preview.data.file_name}`}
          referrerPolicy="no-referrer"
        />
      )}
    </div>
  );
}
