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
  const { language } = useLanguage();
  const search = useMutation({
    mutationFn: (value: string) =>
      apiRequest('/search', searchResponseSchema, {
        method: 'POST',
        body: JSON.stringify({ query: value, language, limit: 8 }),
      }),
  });
  const submit = (event: React.SyntheticEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (query.trim().length > 1) search.mutate(query.trim());
  };
  return (
    <main className="page search-page">
      <span className="eyebrow">Authorized policies</span>
      <h1>Search SOPs</h1>
      <p className="lead">
        Search by question, policy number, phrase, English, Urdu, or Roman Urdu.
      </p>
      <form className="search-box surface" onSubmit={submit}>
        <Search aria-hidden="true" />
        <input
          aria-label="Search SOPs"
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
          }}
          placeholder="What should I do with damaged stock?"
        />
        <button>Search</button>
      </form>
      {search.isPending && (
        <div className="result-skeletons" aria-busy="true">
          <div className="skeleton result-skeleton" />
          <div className="skeleton result-skeleton" />
        </div>
      )}
      {search.isError && (
        <ErrorState
          title="Search is temporarily unavailable"
          detail="Your policy reader remains available. Try the search again shortly."
        />
      )}
      {search.isSuccess && !search.data.results.length && (
        <EmptyState
          title="No guidance found"
          detail="No matching guidance was found in the published SOPs available to you."
        />
      )}
      {search.data?.results.length ? (
        <section className="results" aria-live="polite">
          <div className="results-heading">
            <strong>{search.data.results.length} relevant sections</strong>
            <span>Only authorized published content</span>
          </div>
          {search.data.results.map((evidence) => (
            <SourceCitation evidence={evidence} key={evidence.chunk_id} />
          ))}
        </section>
      ) : null}
    </main>
  );
}
