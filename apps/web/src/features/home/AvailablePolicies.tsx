import { useQuery } from '@tanstack/react-query';
import { ArrowRight, BookOpenText } from 'lucide-react';
import { Link } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { EmptyState, ErrorState } from '../../components/feedback/StatePanel';
import { availablePolicyListSchema } from '../../types/retrieval';
import { useLanguage } from '../language/useLanguage';

export function AvailablePolicies({ limit }: { limit?: number }) {
  const { t } = useLanguage();
  const policies = useQuery({
    queryKey: ['available-policies'],
    queryFn: () => apiRequest('/policies', availablePolicyListSchema),
  });
  const visible = limit ? policies.data?.slice(0, limit) : policies.data;

  if (policies.isPending)
    return (
      <div
        className="available-policy-list"
        aria-label={t('availableSopsLoading')}
      >
        {[1, 2, 3].map((item) => (
          <div className="available-policy-skeleton skeleton" key={item} />
        ))}
      </div>
    );
  if (policies.isError)
    return (
      <ErrorState
        title={t('availableSopsError')}
        detail={t('availableSopsErrorDetail')}
      />
    );
  if (!visible?.length)
    return (
      <EmptyState
        title={t('availableSopsEmpty')}
        detail={t('availableSopsEmptyDetail')}
      />
    );

  return (
    <div className="available-policy-list">
      {visible.map((policy) => (
        <Link
          className="available-policy-card"
          key={policy.policy_id}
          to={`/policies/${policy.policy_id}`}
        >
          <span className="available-policy-icon">
            <BookOpenText aria-hidden="true" />
          </span>
          <span className="available-policy-copy">
            <strong dir="auto">{policy.title}</strong>
            <span>
              {policy.policy_number ? `${policy.policy_number} · ` : ''}
              {policy.category} · {t('availableVersion')} {policy.version_label}
            </span>
            {policy.effective_date && (
              <small>
                {t('availableEffective')} {policy.effective_date}
                {policy.recently_updated ? ` · ${t('availableRecent')}` : ''}
              </small>
            )}
          </span>
          <ArrowRight aria-hidden="true" />
        </Link>
      ))}
    </div>
  );
}
