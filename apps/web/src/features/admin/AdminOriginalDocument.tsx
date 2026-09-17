import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Download, FileText } from 'lucide-react';
import { apiBlob } from '../../api/client';
import { localizedSource, useAdminCopy } from './adminCopy';
import type { PolicyViewer } from '../../types/policy';

type Source = PolicyViewer['sources'][number];
function OriginalAsset({ source, blob }: { source: Source; blob: Blob }) {
  const { copy } = useAdminCopy();
  const [url] = useState(() => URL.createObjectURL(blob));
  useEffect(
    () => () => {
      URL.revokeObjectURL(url);
    },
    [url],
  );
  function download() {
    const link = document.createElement('a');
    link.href = url;
    link.download = source.file_name;
    link.click();
  }
  return (
    <>
      <button type="button" className="reader-download" onClick={download}>
        <Download size={16} /> {copy.downloadOriginal}
      </button>
      {source.media_type === 'application/pdf' && (
        <iframe
          className="original-embed"
          title={`${copy.original}: ${source.file_name}`}
          src={url}
        />
      )}
      {source.media_type.startsWith('image/') && (
        <img
          className="original-image"
          src={url}
          alt={`${copy.original}: ${source.file_name}`}
        />
      )}
      {source.media_type.startsWith('text/') && <TextPreview blob={blob} />}
      {!source.media_type.startsWith('text/') &&
        source.media_type !== 'application/pdf' &&
        !source.media_type.startsWith('image/') && (
          <p className="reader-notice">{copy.previewUnavailable}</p>
        )}
    </>
  );
}
function TextPreview({ blob }: { blob: Blob }) {
  const [text, setText] = useState('');
  useEffect(() => {
    void blob.text().then(setText);
  }, [blob]);
  return (
    <pre className="original-text" dir="auto">
      {text}
    </pre>
  );
}
function SourceFile({ source }: { source: Source }) {
  const { copy } = useAdminCopy();
  const preview = useQuery({
    queryKey: ['admin-original', source.id],
    queryFn: () => apiBlob(`/admin/sources/${source.id}/original`),
    enabled: source.original_allowed,
  });
  return (
    <section className="original-file">
      <div className="original-file-heading">
        <div className="original-file-name">
          <FileText size={21} />
          <div>
            <strong>{source.file_name}</strong>
            <span>
              {localizedSource(source.source_format, copy)} ·{' '}
              {copy.privateOriginal}
            </span>
          </div>
        </div>
      </div>
      {!source.original_allowed && (
        <div className="reader-notice">{copy.originalRestricted}</div>
      )}
      {preview.isPending && source.original_allowed && (
        <div
          className="skeleton skeleton--panel"
          aria-label={copy.originalLoading}
        />
      )}
      {preview.isError && (
        <div className="reader-notice">{copy.originalUnavailable}</div>
      )}
      {preview.data && (
        <OriginalAsset key={source.id} source={source} blob={preview.data} />
      )}
    </section>
  );
}
export function AdminOriginalDocument({
  sources,
}: {
  sources: PolicyViewer['sources'];
}) {
  const { copy } = useAdminCopy();
  if (!sources.length)
    return <div className="reader-notice">{copy.noOriginal}</div>;
  return (
    <div className="original-files">
      {sources.map((source) => (
        <SourceFile key={source.id} source={source} />
      ))}
    </div>
  );
}
