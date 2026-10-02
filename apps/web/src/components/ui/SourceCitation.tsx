import { BookOpenText, ExternalLink } from 'lucide-react';
import { Fragment } from 'react';
import { Link } from 'react-router-dom';
import type { z } from 'zod';
import type { searchEvidenceSchema } from '../../types/retrieval';
import { useLanguage } from '../../features/language/useLanguage';

type Evidence = z.infer<typeof searchEvidenceSchema>;

function escapeExpression(value: string) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

export function HighlightedExcerpt({
  text,
  query,
}: {
  text: string;
  query?: string | undefined;
}) {
  const terms = [
    ...new Set(
      (query ?? '')
        .trim()
        .split(/\s+/u)
        .map((term) => term.trim())
        .filter((term) => term.length > 1),
    ),
  ];
  if (!terms.length) return text;
  const expression = new RegExp(
    `(${terms.map(escapeExpression).join('|')})`,
    'giu',
  );
  return text
    .split(expression)
    .map((part, index) =>
      terms.some(
        (term) => term.toLocaleLowerCase() === part.toLocaleLowerCase(),
      ) ? (
        <mark key={`${part}-${String(index)}`}>{part}</mark>
      ) : (
        <Fragment key={`${part}-${String(index)}`}>{part}</Fragment>
      ),
    );
}

export function SourceCitation({
  evidence,
  query,
}: {
  evidence: Evidence;
  query?: string;
}) {
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
          <HighlightedExcerpt text={evidence.excerpt} query={query} />
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
