import { useQuery } from '@tanstack/react-query';
import { Download, LockKeyhole } from 'lucide-react';
import { useParams, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { policyReaderSchema } from '../../types/retrieval';
import { useLanguage } from '../language/useLanguage';

export default function PolicyPage() {
  const { t } = useLanguage();
  const { policyId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const selectedSection = searchParams.get('section');
  const policy = useQuery({
    queryKey: ['policy', policyId],
    queryFn: () => apiRequest(`/policies/${policyId}`, policyReaderSchema),
  });
  if (policy.isLoading) return <RouteSkeleton />;
  if (policy.isError || !policy.data)
    return (
      <ErrorState
        title={t('policyUnavailable')}
        detail={t('policyErrorDetail')}
      />
    );
  return (
    <main className="page reader-page">
      <header className="reader-heading">
        <div>
          <span className="eyebrow">
            {t('publishedPolicy')} · {policy.data.version_label}
          </span>
          <h1 dir="auto">{policy.data.title}</h1>
          <p dir="auto">{policy.data.category}</p>
          <p className="source-fidelity-note">{t('originalSourceNote')}</p>
        </div>
        <span className="source-lock">
          {policy.data.original_download_allowed ? (
            <>
              <Download />
              {t('fullSource')}
            </>
          ) : (
            <>
              <LockKeyhole />
              {t('canonicalOnly')}
            </>
          )}
        </span>
      </header>
      <div className="reader-layout">
        <aside className="surface reader-toc">
          <strong>{t('onThisPage')}</strong>
          {policy.data.sections.map((section) => (
            <a
              className={section.section_id === selectedSection ? 'active' : ''}
              href={`#${section.section_id}`}
              key={section.section_id}
            >
              <span dir="auto">{section.heading}</span>
            </a>
          ))}
        </aside>
        <article className="surface policy-document">
          {policy.data.sections.map((section) => (
            <section
              id={section.section_id}
              className={
                section.section_id === selectedSection ? 'highlighted' : ''
              }
              key={section.section_id}
            >
              <p className="section-number">{section.policy_number}</p>
              <h2 dir="auto">{section.heading}</h2>
              <div className="policy-copy">
                {section.content.split('\n').map((paragraph) => (
                  <p key={paragraph} dir="auto">
                    {paragraph}
                  </p>
                ))}
              </div>
              <small>
                {section.source.page_start
                  ? `${t('sourcePage')} ${String(section.source.page_start)}`
                  : section.source.sheet_name
                    ? `${section.source.sheet_name} · ${section.source.cell_range ?? ''}`
                    : t('canonicalSection')}
              </small>
            </section>
          ))}
        </article>
      </div>
    </main>
  );
}
