import { useState } from 'react';
import { z } from 'zod';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowLeft,
  ArrowUpRight,
  ChevronDown,
  FileText,
  Filter,
  Plus,
  RotateCcw,
  Search,
  X,
} from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { apiRequest, ApiError } from '../../api/client';
import { EmptyState, ErrorState } from '../../components/feedback/StatePanel';
import { policyListSchema, type Policy } from '../../types/policy';
import { profileSchema } from '../../types/profile';
import { purgeCopy } from './purgeCopy';
import {
  localizedSort,
  localizedSource,
  localizedStatus,
  useAdminCopy,
} from './adminCopy';
import {
  documentStatus,
  formatDate,
  displayVersion,
} from './policyPresentation';

const sorts = [
  'Recently Updated',
  'Title A–Z',
  'Newest Version',
  'Status',
] as const;
function versionOf(policy: Policy) {
  return policy.versions?.find(
    (version) => version.id === policy.display_version_id,
  );
}
function versionNumber(label: string) {
  return Number(label.match(/\d+(?:\.\d+)?/)?.[0] ?? 0);
}
export default function AdminLibraryPage() {
  const { copy, language } = useAdminCopy();
  const location = useLocation();
  const [search, setSearch] = useState('');
  const defaultStatus = location.pathname.endsWith('/review-queue')
    ? 'Review Required'
    : 'current';
  const [status, setStatus] = useState(defaultStatus);
  const [department, setDepartment] = useState('all');
  const [sourceType, setSourceType] = useState('all');
  const [updated, setUpdated] = useState('all');
  const [sort, setSort] = useState<(typeof sorts)[number]>('Recently Updated');
  const [referenceTime] = useState(() => Date.now());
  const policies = useQuery({
    queryKey: ['admin-policies'],
    queryFn: () => apiRequest('/admin/policies', policyListSchema),
  });
  const profile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });
  const canIngest = profile.data?.application_roles.includes('system_admin');
  const data = policies.data ?? [];
  const departments = [
    ...new Set(
      data.flatMap((policy) => {
        const dimension = versionOf(policy)?.access.departments;
        return dimension?.mode === 'selected' ? dimension.values : [];
      }),
    ),
  ].sort();
  const sourceTypes = [
    ...new Set(
      data.flatMap(
        (policy) => policy.sources?.map((source) => source.source_format) ?? [],
      ),
    ),
  ].sort();
  const departmentCount = (name: string) =>
    data.filter((policy) => {
      const scope = versionOf(policy)?.access.departments;
      return (
        name === 'all' || scope?.mode === 'all' || scope?.values.includes(name)
      );
    }).length;
  const visible = data
    .filter((policy) => {
      const version = versionOf(policy);
      const query = search.trim().toLocaleLowerCase();
      const matches =
        !query ||
        [
          policy.title,
          policy.policy_number ?? '',
          ...(policy.sources?.map((source) => source.file_name) ?? []),
        ].some((value) => value.toLocaleLowerCase().includes(query));
      const scope = version?.access.departments;
      const date = Date.parse(policy.updated_at);
      const days = updated === '30' ? 30 : updated === '90' ? 90 : null;
      return (
        matches &&
        (status === 'all' ||
          (status === 'current' && policy.status !== 'inactive') ||
          documentStatus(
            version?.status ?? policy.status,
            policy.sources?.map((source) => source.status) ?? [],
            policy.status,
          ) === status) &&
        (department === 'all' ||
          scope?.mode === 'all' ||
          scope?.values.includes(department)) &&
        (sourceType === 'all' ||
          policy.sources?.some(
            (source) => source.source_format === sourceType,
          )) &&
        (!days || date >= referenceTime - days * 86_400_000)
      );
    })
    .sort((a, b) => {
      if (sort === 'Title A–Z') return a.title.localeCompare(b.title);
      if (sort === 'Newest Version')
        return (
          versionNumber(versionOf(b)?.version_label ?? '') -
          versionNumber(versionOf(a)?.version_label ?? '')
        );
      if (sort === 'Status')
        return documentStatus(
          versionOf(a)?.status ?? a.status,
          a.sources?.map((source) => source.status) ?? [],
          a.status,
        ).localeCompare(
          documentStatus(
            versionOf(b)?.status ?? b.status,
            b.sources?.map((source) => source.status) ?? [],
            b.status,
          ),
        );
      return Date.parse(b.updated_at) - Date.parse(a.updated_at);
    });
  const hasActiveFilters = Boolean(
    search.trim() ||
    status !== defaultStatus ||
    department !== 'all' ||
    sourceType !== 'all' ||
    updated !== 'all' ||
    sort !== 'Recently Updated',
  );
  const handleResetFilters = () => {
    setSearch('');
    setStatus(defaultStatus);
    setDepartment('all');
    setSourceType('all');
    setUpdated('all');
    setSort('Recently Updated');
  };
  return (
    <section
      className="admin-content library-page"
      aria-labelledby="library-title"
    >
      {z.object({ purged: z.literal(true) }).safeParse(location.state)
        .success && <p role="status">{purgeCopy[language].success}</p>}
      <div className="library-toolbar">
        <div className="library-toolbar-content">
          <Link
            to="/home"
            className="library-back-link"
            aria-label={copy.backToHome}
          >
            <ArrowLeft size={15} aria-hidden="true" />
            <span>{copy.backToHome}</span>
          </Link>
          <div className="library-heading-group">
            <span className="eyebrow eyebrow--pill">{copy.management}</span>
            <h2 id="library-title">{copy.navLibrary}</h2>
            <p>{copy.libraryIntro}</p>
          </div>
        </div>
        {canIngest && (
          <Link
            className="button button--primary library-add-btn"
            to="/admin/add"
          >
            <Plus size={16} aria-hidden="true" />
            <span>{copy.addSop}</span>
          </Link>
        )}
      </div>
      <div className="library-filter surface">
        <div className="library-search-wrapper">
          <label className="library-search">
            <Search
              size={18}
              className="library-search-icon"
              aria-hidden="true"
            />
            <span className="sr-only">{copy.search}</span>
            <input
              type="search"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
              }}
              placeholder={copy.search}
            />
            {search && (
              <button
                type="button"
                className="library-search-clear"
                aria-label={copy.clearSearch}
                onClick={() => {
                  setSearch('');
                }}
              >
                <X size={15} />
              </button>
            )}
          </label>
        </div>
        <div className="library-departments" aria-label={copy.department}>
          <button
            type="button"
            className={department === 'all' ? 'selected' : ''}
            onClick={() => {
              setDepartment('all');
            }}
          >
            {copy.allDepartments} <span>{departmentCount('all')}</span>
          </button>
          {departments.map((item) => (
            <button
              type="button"
              className={department === item ? 'selected' : ''}
              key={item}
              onClick={() => {
                setDepartment(item);
              }}
            >
              {item} <span>{departmentCount(item)}</span>
            </button>
          ))}
        </div>
        <div className="library-selects">
          <label
            className={`library-select-label${status !== defaultStatus ? ' active-filter' : ''}`}
          >
            <span className="library-select-title">
              {copy.status}
              {status !== defaultStatus && (
                <span className="active-dot" aria-hidden="true" />
              )}
            </span>
            <div className="library-select-container">
              <select
                value={status}
                onChange={(event) => {
                  setStatus(event.target.value);
                }}
              >
                <option value="current">{copy.currentPolicies}</option>
                <option value="all">{copy.allStatuses}</option>
                {[
                  'Published',
                  'Draft',
                  'Processing',
                  'Review Required',
                  'Ready for Review',
                  'Approved',
                  'Ready to Publish',
                  'Failed',
                  'Superseded',
                  'Inactive / Archived',
                ].map((item) => (
                  <option key={item} value={item}>
                    {localizedStatus(item, copy)}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="library-select-chevron"
                aria-hidden="true"
              />
            </div>
          </label>
          <label
            className={`library-select-label${sourceType !== 'all' ? ' active-filter' : ''}`}
          >
            <span className="library-select-title">
              {copy.sourceType}
              {sourceType !== 'all' && (
                <span className="active-dot" aria-hidden="true" />
              )}
            </span>
            <div className="library-select-container">
              <select
                value={sourceType}
                onChange={(event) => {
                  setSourceType(event.target.value);
                }}
              >
                <option value="all">{copy.allTypes}</option>
                {sourceTypes.map((item) => (
                  <option key={item} value={item}>
                    {localizedSource(item, copy)}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="library-select-chevron"
                aria-hidden="true"
              />
            </div>
          </label>
          <label
            className={`library-select-label${updated !== 'all' ? ' active-filter' : ''}`}
          >
            <span className="library-select-title">
              {copy.updated}
              {updated !== 'all' && (
                <span className="active-dot" aria-hidden="true" />
              )}
            </span>
            <div className="library-select-container">
              <select
                value={updated}
                onChange={(event) => {
                  setUpdated(event.target.value);
                }}
              >
                <option value="all">{copy.anyTime}</option>
                <option value="30">{copy.past30}</option>
                <option value="90">{copy.past90}</option>
              </select>
              <ChevronDown
                size={14}
                className="library-select-chevron"
                aria-hidden="true"
              />
            </div>
          </label>
          <label
            className={`library-select-label${sort !== 'Recently Updated' ? ' active-filter' : ''}`}
          >
            <span className="library-select-title">
              {copy.sort}
              {sort !== 'Recently Updated' && (
                <span className="active-dot" aria-hidden="true" />
              )}
            </span>
            <div className="library-select-container">
              <select
                value={sort}
                onChange={(event) => {
                  setSort(event.target.value as (typeof sorts)[number]);
                }}
              >
                {sorts.map((item) => (
                  <option key={item} value={item}>
                    {localizedSort(item, copy)}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="library-select-chevron"
                aria-hidden="true"
              />
            </div>
          </label>
        </div>
        {hasActiveFilters && (
          <div className="library-active-filters-bar">
            <span className="library-active-filters-label">
              <Filter size={13} aria-hidden="true" />
              <span>{copy.filters}:</span>
            </span>
            <div className="library-active-chips">
              {search.trim() && (
                <button
                  type="button"
                  className="library-active-chip"
                  onClick={() => {
                    setSearch('');
                  }}
                  title={copy.resetSearch}
                  aria-label={copy.resetSearch}
                >
                  <span>"{search.trim()}"</span>
                  <X size={11} aria-hidden="true" />
                </button>
              )}
              {department !== 'all' && (
                <button
                  type="button"
                  className="library-active-chip"
                  onClick={() => {
                    setDepartment('all');
                  }}
                  title={copy.resetDepartment}
                  aria-label={copy.resetDepartment}
                >
                  <span>{department}</span>
                  <X size={11} aria-hidden="true" />
                </button>
              )}
              {status !== defaultStatus && (
                <button
                  type="button"
                  className="library-active-chip"
                  onClick={() => {
                    setStatus(defaultStatus);
                  }}
                  title={copy.resetStatus}
                  aria-label={copy.resetStatus}
                >
                  <span>
                    {status === 'all'
                      ? copy.allStatuses
                      : status === 'current'
                        ? copy.currentPolicies
                        : localizedStatus(status, copy)}
                  </span>
                  <X size={11} aria-hidden="true" />
                </button>
              )}
              {sourceType !== 'all' && (
                <button
                  type="button"
                  className="library-active-chip"
                  onClick={() => {
                    setSourceType('all');
                  }}
                  title={copy.resetSource}
                  aria-label={copy.resetSource}
                >
                  <span>{localizedSource(sourceType, copy)}</span>
                  <X size={11} aria-hidden="true" />
                </button>
              )}
              {updated !== 'all' && (
                <button
                  type="button"
                  className="library-active-chip"
                  onClick={() => {
                    setUpdated('all');
                  }}
                  title={copy.resetUpdated}
                  aria-label={copy.resetUpdated}
                >
                  <span>{updated === '30' ? copy.past30 : copy.past90}</span>
                  <X size={11} aria-hidden="true" />
                </button>
              )}
              {sort !== 'Recently Updated' && (
                <button
                  type="button"
                  className="library-active-chip"
                  title={copy.resetSort}
                  aria-label={copy.resetSort}
                  onClick={() => {
                    setSort('Recently Updated');
                  }}
                >
                  <span>{localizedSort(sort, copy)}</span>
                  <X size={11} aria-hidden="true" />
                </button>
              )}
            </div>
            <button
              type="button"
              className="library-reset-all-btn"
              onClick={handleResetFilters}
            >
              <RotateCcw size={12} aria-hidden="true" />
              <span>{copy.clearFilters}</span>
            </button>
          </div>
        )}
      </div>
      {policies.isPending && (
        <div className="library-results surface" aria-label={copy.loadingSops}>
          <div className="library-results-heading skeleton" />
          {[1, 2, 3, 4].map((item) => (
            <div key={item} className="library-card-skeleton">
              <div className="skeleton" />
              <div className="skeleton" />
            </div>
          ))}
        </div>
      )}
      {policies.isError && (
        <ErrorState
          title={
            policies.error instanceof ApiError && policies.error.status === 403
              ? copy.adminRequired
              : copy.libraryUnavailable
          }
          detail={copy.libraryError}
        />
      )}
      {policies.isSuccess && (
        <div className="library-results surface">
          <div className="library-results-heading">
            <h3>{copy.sops}</h3>
            <span>
              {visible.length}{' '}
              {visible.length === 1 ? copy.document : copy.documents}
            </span>
          </div>
          {visible.map((policy) => {
            const version = versionOf(policy);
            const label = documentStatus(
              version?.status ?? policy.status,
              policy.sources?.map((source) => source.status) ?? [],
              policy.status,
            );
            const scope = version?.access.departments;
            const reviewSource = policy.sources?.find(
              (source) =>
                source.status === 'review_required' && source.original_allowed,
            );
            return (
              <article className="library-card" key={policy.id}>
                <span className="library-file-icon">
                  <FileText size={21} />
                </span>
                <span className="library-card-main">
                  <strong>
                    <Link to={`/admin/policies/${policy.id}`}>
                      {policy.title}
                    </Link>
                  </strong>
                  <span className="library-card-meta">
                    {policy.policy_number && (
                      <span>{policy.policy_number} · </span>
                    )}
                    {displayVersion(
                      version?.version_label,
                      copy.versionLabel,
                      copy.noVersion,
                    )}{' '}
                    ·{' '}
                    <span
                      className={`status-text status-text--${label.toLowerCase().replaceAll(' ', '-')}`}
                    >
                      {localizedStatus(label, copy)}
                    </span>
                    {policy.sources?.[0] && (
                      <>
                        {' '}
                        ·{' '}
                        {localizedSource(policy.sources[0].source_format, copy)}
                      </>
                    )}{' '}
                    · {copy.updatedOn} {formatDate(policy.updated_at, language)}
                  </span>
                  <span className="library-card-details">
                    {policy.section_count ?? 0} {copy.sections}
                    {policy.page_count
                      ? ` · ${String(policy.page_count)} ${copy.pages}`
                      : ''}
                    {scope && (
                      <>
                        {' '}
                        ·{' '}
                        {scope.mode === 'all'
                          ? copy.allDepartments
                          : scope.values.join(', ')}
                      </>
                    )}
                    {policy.sources?.[0] && (
                      <> · {policy.sources[0].file_name}</>
                    )}
                  </span>
                  {label === 'Failed' && (
                    <span className="library-failure">
                      {copy.processingFailed} · {copy.openDetails}
                    </span>
                  )}
                </span>
                <span className="library-card-actions">
                  {reviewSource && (
                    <Link
                      className="library-review"
                      to={`/admin/review/${reviewSource.id}`}
                    >
                      {copy.reviewSource}
                    </Link>
                  )}
                  <Link
                    className="library-open"
                    to={`/admin/policies/${policy.id}`}
                    aria-label={`${copy.open} ${policy.title}`}
                  >
                    {copy.open} <ArrowUpRight size={17} />
                  </Link>
                </span>
              </article>
            );
          })}
          {!data.length && (
            <div className="library-empty">
              <EmptyState title={copy.noSops} detail={copy.noSopsDetail} />
              {canIngest && (
                <Link className="button button--primary" to="/admin/add">
                  {copy.addSop}
                </Link>
              )}
            </div>
          )}
          {!!data.length && !visible.length && (
            <div className="library-empty">
              <EmptyState
                title={copy.noMatches}
                detail={copy.noMatchesDetail}
              />
              <button
                type="button"
                className="library-clear"
                onClick={handleResetFilters}
              >
                {copy.clearFilters}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
