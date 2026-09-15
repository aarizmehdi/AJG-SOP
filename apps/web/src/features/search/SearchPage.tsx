import { useMutation } from '@tanstack/react-query';
import { Search } from 'lucide-react';
import { useState } from 'react';
import { apiRequest } from '../../api/client';
import { EmptyState, ErrorState } from '../../components/feedback/StatePanel';
import { SourceCitation } from '../../components/ui/SourceCitation';
import { searchResponseSchema } from '../../types/retrieval';
import { useLanguage } from '../language/useLanguage';

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const { language, t } = useLanguage();
  const search = useMutation({
    mutationFn: (value: string) =>
      apiRequest('/search', searchResponseSchema, {
        method: 'POST',
        body: JSON.stringify({ query: value, language, limit: 8 }),
      }),
  });
  const submit = (event: React.SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (query.trim() && !search.isPending) search.mutate(query.trim());
  };
  return (
    <main className="page search-page">
      <span className="eyebrow">{t('searchEyebrow')}</span>
      <h1>{t('searchTitle')}</h1>
      <p className="lead">{t('searchLead')}</p>
      <form className="search-box surface" onSubmit={submit}>
        <Search aria-hidden="true" />
        <input
          aria-label={t('searchNav')}
          dir="auto"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
          placeholder={t('searchPlaceholder')}
        />
        <button disabled={search.isPending || !query.trim()}>
          {t('searchButton')}
        </button>
      </form>
      {search.isPending && (
        <div
          className="result-skeletons"
          aria-busy="true"
          aria-label={t('searchLoading')}
        >
          <div className="skeleton result-skeleton" />
          <div className="skeleton result-skeleton" />
        </div>
      )}
      {search.isError && (
        <ErrorState
          title={t('searchUnavailable')}
          detail={t('searchErrorDetail')}
        />
      )}
      {search.isSuccess && !search.data.results.length && (
        <EmptyState
          title={t('searchEmptyTitle')}
          detail={t('searchEmptyDetail')}
        />
      )}
      {search.data?.results.length ? (
        <section className="results" aria-live="polite">
          <div className="results-heading">
            <strong>
              {search.data.results.length} {t('searchRelevant')}
            </strong>
            <span>{t('searchAuthorized')}</span>
          </div>
          {search.data.results.map((evidence) => (
            <SourceCitation evidence={evidence} key={evidence.chunk_id} />
          ))}
        </section>
      ) : null}
    </main>
  );
}
