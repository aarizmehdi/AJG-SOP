import { useQuery } from '@tanstack/react-query';
import { Download, LockKeyhole } from 'lucide-react';
import { useParams, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { policyReaderSchema } from '../../types/retrieval';

export default function PolicyPage() {
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
        title="Policy unavailable"
        detail="The policy does not exist or is outside your current access scope."
      />
    );
  return (
    <main className="page reader-page">
      <header className="reader-heading">
        <div>
          <span className="eyebrow">
            Published policy · {policy.data.version_label}
          </span>
          <h1>{policy.data.title}</h1>
          <p>{policy.data.category}</p>
        </div>
        <span className="source-lock">
          {policy.data.original_download_allowed ? (
            <>
              <Download />
              Full source authorized
            </>
          ) : (
            <>
              <LockKeyhole />
              Canonical sections only
            </>
          )}
        </span>
      </header>
      <div className="reader-layout">
        <aside className="surface reader-toc">
          <strong>On this page</strong>
          {policy.data.sections.map((section) => (
            <a
              className={section.section_id === selectedSection ? 'active' : ''}
              href={`#${section.section_id}`}
              key={section.section_id}
            >
              {section.heading}
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
              <h2>{section.heading}</h2>
              <div className="policy-copy">
                {section.content.split('\n').map((paragraph) => (
                  <p key={paragraph}>{paragraph}</p>
                ))}
              </div>
              <small>
                {section.source.page_start
                  ? `Source page ${String(section.source.page_start)}`
                  : section.source.sheet_name
                    ? `${section.source.sheet_name} · ${section.source.cell_range ?? ''}`
                    : 'Canonical source section'}
              </small>
            </section>
          ))}
        </article>
      </div>
    </main>
  );
}
