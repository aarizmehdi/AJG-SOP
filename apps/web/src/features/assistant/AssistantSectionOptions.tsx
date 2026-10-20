import { Link } from 'react-router-dom';
import type { StreamAnswer } from '../../types/assistant';
import { useLanguage } from '../language/useLanguage';

export function AssistantSectionOptions({
  sections,
  onAsk,
}: {
  sections: StreamAnswer['section_options'];
  onAsk: (question: string) => void;
}) {
  const { t } = useLanguage();
  if (!sections.length) return null;
  return (
    <div className="assistant-section-options">
      <ol>
        {sections.map((section) => (
          <li key={`${section.policy_id}:${section.section_id}`}>
            <Link
              to={`/policies/${encodeURIComponent(section.policy_id)}?section=${encodeURIComponent(section.section_id)}`}
            >
              <strong dir="auto">{section.heading}</strong>
              <small dir="auto">{section.policy_title}</small>
            </Link>
            <button
              type="button"
              onClick={() => {
                onAsk(`${section.policy_title} — ${section.heading}`);
              }}
              aria-label={`${t('assistantAskSection')}: ${section.heading}`}
            >
              {t('assistantAskSection')}
            </button>
          </li>
        ))}
      </ol>
      {[
        ...new Map(sections.map((item) => [item.policy_id, item])).values(),
      ].map((policy) => (
        <Link
          key={policy.policy_id}
          to={`/policies/${encodeURIComponent(policy.policy_id)}`}
        >
          {t('assistantOpenFullPolicy')} · {policy.policy_title}
        </Link>
      ))}
    </div>
  );
}
