import { FileText } from 'lucide-react';
import type { PolicyViewer } from '../../types/policy';
import { localizedSource, useAdminCopy } from './adminCopy';
import { OriginalPreview } from './OriginalPreview';

export function AdminOriginalDocument({
  sources,
  versionStatus,
}: {
  sources: PolicyViewer['sources'];
  versionStatus: string;
}) {
  const { copy } = useAdminCopy();
  if (!sources.length)
    return <div className="reader-notice">{copy.noOriginal}</div>;
  return (
    <div className="original-files">
      {sources.map((source) => (
        <section className="original-file" key={source.id}>
          <div className="original-file-heading">
            <div className="original-file-name">
              <FileText size={21} />
              <div>
                <strong>
                  {source.source_format === 'markdown' &&
                  !source.structured_file_name
                    ? copy.originalNeedsVerification
                    : source.file_name}
                </strong>
                <span>
                  {localizedSource(source.source_format, copy)} ·{' '}
                  {copy.privateLabel}
                </span>
                {source.structured_file_name && (
                  <small>
                    {copy.structuredSource}: {source.structured_file_name}
                  </small>
                )}
              </div>
            </div>
          </div>
          {source.original_allowed ? (
            <OriginalPreview
              sourceId={source.id}
              canAttach={
                source.source_format === 'markdown' &&
                !source.structured_file_name &&
                !['published', 'superseded'].includes(versionStatus)
              }
            />
          ) : (
            <div className="reader-notice">{copy.originalRestricted}</div>
          )}
        </section>
      ))}
    </div>
  );
}
