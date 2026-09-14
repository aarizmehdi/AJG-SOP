import { BookOpenText, ExternalLink } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { z } from 'zod';
import type { searchEvidenceSchema } from '../../types/retrieval';

type Evidence = z.infer<typeof searchEvidenceSchema>;

export function SourceCitation({ evidence }: { evidence: Evidence }) {
  const location = evidence.source.page_start
    ? `Page ${String(evidence.source.page_start)}`
    : evidence.source.sheet_name
      ? `${evidence.source.sheet_name} · ${evidence.source.cell_range ?? 'sheet'}`
      : 'Source section';
  return (
    <article className="search-result surface">
      <div className="result-icon">
        <BookOpenText />
      </div>
      <div>
        <div className="result-meta">
          <span>{evidence.policy_title}</span>
          <span>{location}</span>
        </div>
        <h2>{evidence.heading_path.at(-1)}</h2>
        <p className="breadcrumb">{evidence.heading_path.join(' → ')}</p>
        <p className="excerpt">{evidence.excerpt}</p>
        <Link
          to={`/policies/${evidence.policy_id}?section=${evidence.section_id}`}
        >
          View policy <ExternalLink size={14} />
        </Link>
      </div>
    </article>
  );
}
