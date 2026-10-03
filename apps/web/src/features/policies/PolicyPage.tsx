import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import {
  CanonicalDocumentRenderer,
  type CanonicalSectionView,
} from '../../components/documents/CanonicalDocumentRenderer';
import { canonicalSectionDomId } from '../../components/documents/canonicalDocumentIds';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { policyReaderSchema } from '../../types/retrieval';
import { useLanguage } from '../language/useLanguage';

export default function PolicyPage() {
  const { t } = useLanguage();
  const { policyId = '' } = useParams();
  const [searchParams] = useSearchParams();
  const selectedSection = searchParams.get('section');
  const [focusedSection, setFocusedSection] = useState<string | null>(
    selectedSection,
  );
  const policy = useQuery({
    queryKey: ['policy', policyId],
    queryFn: () => apiRequest(`/policies/${policyId}`, policyReaderSchema),
  });
  const sections = useMemo<CanonicalSectionView[]>(
    () =>
      policy.data?.sections.map((section) => ({
        ...section,
        blocks:
          section.blocks.length > 0
            ? section.blocks
            : section.content
                .split('\n')
                .filter(Boolean)
                .map((text, index) => ({
                  id: `legacy-${section.section_id}-${String(index)}`,
                  kind: 'paragraph' as const,
                  text,
                  list_items: [],
                  table: null,
                })),
        id: section.section_id,
      })) ?? [],
    [policy.data],
  );

  useEffect(() => {
    if (!policy.data || !selectedSection) return;
    const scrollTimer = window.setTimeout(() => {
      setFocusedSection(selectedSection);
      const target = document.getElementById(
        canonicalSectionDomId('policy-section', selectedSection),
      );
      target?.scrollIntoView({
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'auto'
          : 'smooth',
        block: 'center',
      });
      target?.focus({ preventScroll: true });
    }, 0);
    const clearTimer = window.setTimeout(() => {
      setFocusedSection((current) =>
        current === selectedSection ? null : current,
      );
    }, 4000);
    return () => {
      window.clearTimeout(scrollTimer);
      window.clearTimeout(clearTimer);
    };
  }, [policy.data, selectedSection]);

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
      </header>
      <div className="reader-layout">
        <aside className="surface reader-toc">
          <strong>{t('onThisPage')}</strong>
          {policy.data.sections.map((section) => (
            <Link
              className={section.section_id === selectedSection ? 'active' : ''}
              style={{
                paddingInlineStart: `${String(
                  8 + Math.max(0, section.heading_level - 1) * 12,
                )}px`,
              }}
              to={`/policies/${policyId}?section=${encodeURIComponent(
                section.section_id,
              )}`}
              key={section.section_id}
            >
              <span dir="auto">{section.heading}</span>
            </Link>
          ))}
        </aside>
        <article className="surface policy-document">
          <CanonicalDocumentRenderer
            sections={sections}
            idPrefix="policy-section"
            highlightedSectionId={focusedSection}
            sourceLabel={(section) =>
              section.source.page_start
                ? `${t('sourcePage')} ${String(section.source.page_start)}`
                : section.source.sheet_name
                  ? `${section.source.sheet_name} · ${section.source.cell_range ?? ''}`
                  : t('canonicalSection')
            }
          />
        </article>
      </div>
    </main>
  );
}
