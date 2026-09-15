import { BookOpenText, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { z } from 'zod';
import type { searchEvidenceSchema } from '../../types/retrieval';
import { useLanguage } from '../../features/language/useLanguage';

type Evidence = z.infer<typeof searchEvidenceSchema>;

export function SourceCitation({ evidence }: { evidence: Evidence }) {
  const { t } = useLanguage();
  const location = evidence.source.page_start
    ? `${t('sourcePage')} ${String(evidence.source.page_start)}`
    : evidence.source.sheet_name
      ? `${evidence.source.sheet_name} · ${evidence.source.cell_range ?? t('sourceSheet')}`
      : t('sourceSection');
  return (
    <article className="search-result surface">
      <div className="result-icon">
        <BookOpenText />
      </div>
      <div>
        <div className="result-meta">
          <span dir="auto">{evidence.policy_title}</span>
          <span>{location}</span>
        </div>
        <h2 dir="auto">{evidence.heading_path.at(-1)}</h2>
        <p className="breadcrumb" dir="auto">
          {evidence.heading_path.join(' → ')}
        </p>
        <p className="excerpt" dir="auto">
          {evidence.excerpt}
        </p>
        <Link
          to={`/policies/${evidence.policy_id}?section=${evidence.section_id}`}
        >
          {t('viewPolicy')} <ExternalLink size={14} aria-hidden="true" />
        </Link>
      </div>
    </article>
  );
}
