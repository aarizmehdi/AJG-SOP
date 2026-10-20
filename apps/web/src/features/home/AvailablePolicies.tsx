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
      <div className="sop-card-grid" aria-label={t('availableSopsLoading')}>
        {[1, 2, 3].map((item) => (
          <div className="sop-card-skeleton skeleton" key={item} />
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
    <div className="sop-card-grid">
      {visible.map((policy) => (
        <Link
          className="sop-card"
          key={policy.policy_id}
          to={`/policies/${policy.policy_id}`}
        >
          {/* Left icon badge */}
          <span className="sop-card-icon">
            <BookOpenText aria-hidden="true" size={20} />
          </span>

          {/* Content block */}
          <span className="sop-card-info">
            <strong dir="auto">{policy.title}</strong>
          </span>

          {/* Right arrow button */}
          <span className="sop-card-arrow-btn">
            <ArrowRight
              size={16}
              aria-hidden="true"
              className="sop-card-arrow"
            />
          </span>
        </Link>
      ))}
    </div>
  );
}
