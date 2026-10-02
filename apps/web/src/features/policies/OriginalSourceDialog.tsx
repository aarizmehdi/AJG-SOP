import { useQuery } from '@tanstack/react-query';
import { Download, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { apiBlob } from '../../api/client';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import type { ReaderSource } from '../../types/retrieval';
import { useLanguage } from '../language/useLanguage';

function OriginalContent({
  blob,
  source,
}: {
  blob: Blob;
  source: ReaderSource;
}) {
  const [url] = useState(() => URL.createObjectURL(blob));
  const [text, setText] = useState('');
  useEffect(
    () => () => {
      URL.revokeObjectURL(url);
    },
    [url],
  );
  useEffect(() => {
    if (source.media_type.startsWith('text/')) void blob.text().then(setText);
  }, [blob, source.media_type]);
  if (source.media_type === 'application/pdf')
    return (
      <iframe
        className="employee-original-frame"
        src={url}
        title={source.file_name}
      />
    );
  if (source.media_type.startsWith('image/'))
    return (
      <img
        className="employee-original-image"
        src={url}
        alt={source.file_name}
      />
    );
  if (source.media_type.startsWith('text/'))
    return (
      <pre className="employee-original-text" dir="auto">
        {text}
      </pre>
    );
  return (
    <a
      className="button button--primary"
      href={url}
      download={source.file_name}
    >
      <Download size={17} aria-hidden="true" /> {source.file_name}
    </a>
  );
}

export function OriginalSourceDialog({
  policyId,
  source,
  onClose,
}: {
  policyId: string;
  source: ReaderSource;
  onClose: () => void;
}) {
  const { t } = useLanguage();
  const original = useQuery({
    queryKey: ['employee-original', policyId, source.source_id],
    queryFn: () =>
      apiBlob(
        `/policies/${encodeURIComponent(policyId)}/sources/${encodeURIComponent(source.source_id)}`,
      ),
  });
  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [onClose]);
  return (
    <div
      className="employee-original-backdrop"
      role="presentation"
      onMouseDown={onClose}
    >
      <section
        className="employee-original-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="employee-original-title"
        onMouseDown={(event) => {
          event.stopPropagation();
        }}
      >
        <header>
          <div>
            <span className="eyebrow">
              {source.media_type === 'application/pdf'
                ? t('viewOriginalPdf')
                : t('viewSourceFile')}
            </span>
            <h2 id="employee-original-title" dir="auto">
              {source.file_name}
            </h2>
          </div>
          <button
            type="button"
            aria-label={t('closeOriginal')}
            onClick={onClose}
          >
            <X aria-hidden="true" />
          </button>
        </header>
        <div className="employee-original-content">
          {original.isPending && <RouteSkeleton label={t('originalLoading')} />}
          {original.isError && <p role="alert">{t('originalUnavailable')}</p>}
          {original.data && (
            <OriginalContent blob={original.data} source={source} />
          )}
        </div>
      </section>
    </div>
  );
}
