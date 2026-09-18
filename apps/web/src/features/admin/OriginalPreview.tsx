import { useQuery } from '@tanstack/react-query';
import { FileCheck2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import { apiBlob } from '../../api/client';
import type { reviewPayloadSchema } from '../../types/source';
import { useAdminCopy } from './adminCopy';

type Review = ReturnType<typeof reviewPayloadSchema.parse>;

function BlobPreview({
  blob,
  mediaType,
  title,
  originalSource,
}: {
  blob: Blob;
  mediaType: string;
  title: string;
  originalSource: string;
}) {
  const [url] = useState(() => URL.createObjectURL(blob));
  useEffect(
    () => () => {
      URL.revokeObjectURL(url);
    },
    [url],
  );
  if (mediaType.startsWith('image/'))
    return (
      <img
        className="source-image"
        src={url}
        alt={`${originalSource}: ${title}`}
      />
    );
  return (
    <object
      className="source-object"
      data={url}
      type={mediaType}
      aria-label={`${originalSource}: ${title}`}
    />
  );
}

export function OriginalPreview({
  sourceId,
  source,
  raw,
}: {
  sourceId: string;
  source: Review['source'];
  raw: Review['raw'];
}) {
  const { copy } = useAdminCopy();
  const preview = useQuery({
    queryKey: ['source-original', sourceId],
    queryFn: async () => {
      const blob = await apiBlob(`/admin/sources/${sourceId}/original`);
      return {
        blob,
        text: source.media_type.startsWith('text/') ? await blob.text() : null,
      };
    },
  });
  if (preview.isPending)
    return (
      <div className="source-preview">
        <div className="skeleton skeleton--panel" />
      </div>
    );
  if (preview.isError)
    return (
      <div className="source-preview">
        <FileCheck2 />
        <strong>{copy.originalUnavailable}</strong>
        <p>{copy.previewUnavailable}</p>
      </div>
    );
  if (preview.data.text !== null)
    return <pre className="source-text">{preview.data.text}</pre>;
  if (
    source.media_type === 'application/pdf' ||
    source.media_type.startsWith('image/')
  )
    return (
      <div className="source-preview source-preview--document">
        <BlobPreview
          blob={preview.data.blob}
          mediaType={source.media_type}
          title={source.file_name}
          originalSource={copy.originalSource}
        />
      </div>
    );
  return (
    <div className="source-preview source-preview--structured">
      <strong>{copy.originalStructuredView}</strong>
      {raw?.blocks.map((block, index) =>
        block.table_cells.length ? (
          <div
            className="source-table"
            key={`${block.sheet_name ?? 'table'}-${String(index)}`}
          >
            <b>
              {block.sheet_name ?? 'Table'} · {block.cell_range ?? ''}
            </b>
            {block.table_cells.map((cell) => (
              <span key={`${String(cell.row)}-${String(cell.column)}`}>
                <small>{cell.cell_reference}</small>
                {cell.text}
              </span>
            ))}
          </div>
        ) : (
          <p key={`${block.kind}-${String(index)}`}>{block.text}</p>
        ),
      )}
    </div>
  );
}
