import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Archive,
  ArrowLeft,
  ChevronDown,
  FileText,
  History,
} from 'lucide-react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { apiRequest, ApiError } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { AdminCanonicalReader } from './AdminCanonicalReader';
import { AdminOriginalDocument } from './AdminOriginalDocument';
import { localizedSource, localizedStatus, useAdminCopy } from './adminCopy';
import {
  viewerSchema,
  policySchema,
  type PolicyViewer,
  type AccessScope,
} from '../../types/policy';
import { profileSchema } from '../../types/profile';
import {
  displayVersion,
  formatDate,
  statusLabel,
  documentStatus,
} from './policyPresentation';

const tabs = ['Content', 'Original Document'] as const;
type Tab = (typeof tabs)[number];
function scopeText(
  dimension: AccessScope['departments'],
  label: string,
  all: string,
  selected: string,
) {
  return dimension.mode === 'all'
    ? `${all} ${label}`
    : `${selected} ${label}: ${dimension.values.join(', ')}`;
}
function DetailRow({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  if (value === null || value === undefined || value === '') return null;
  return (
    <div className="admin-detail-row">
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  );
}
function Details({ viewer }: { viewer: PolicyViewer }) {
  const { copy, language } = useAdminCopy();
  const { policy, version, sources } = viewer;
  return (
    <div className="admin-details">
      <h3>{copy.documentInformation}</h3>
      <dl>
        <DetailRow label={copy.sopTitle} value={policy.title} />
        <DetailRow label={copy.policyNumber} value={policy.policy_number} />
        <DetailRow
          label={copy.sourceDocument}
          value={sources.map((source) => source.file_name).join(', ')}
        />
        <DetailRow
          label={copy.sourceType}
          value={sources
            .map((source) => localizedSource(source.source_format, copy))
            .join(', ')}
        />
        <DetailRow
          label={copy.currentSelection}
          value={displayVersion(
            version.version_label,
            copy.versionLabel,
            copy.noVersion,
          )}
        />
        <DetailRow
          label={copy.status}
          value={localizedStatus(
            documentStatus(
              version.status,
              sources.map((source) => source.status),
              policy.status,
            ),
            copy,
          )}
        />
        <DetailRow
          label={copy.created}
          value={formatDate(policy.created_at, language)}
        />
        <DetailRow
          label={copy.updated}
          value={formatDate(policy.updated_at, language)}
        />
        <DetailRow
          label={copy.department}
          value={scopeText(
            version.access.departments,
            copy.departments,
            copy.all,
            copy.selected,
          )}
        />
        <DetailRow
          label={copy.accessScope}
          value={
            <>
              {scopeText(
                version.access.locations,
                copy.locations,
                copy.all,
                copy.selected,
              )}
              <br />
              {scopeText(
                version.access.roles,
                copy.roles,
                copy.all,
                copy.selected,
              )}
            </>
          }
        />
        <DetailRow label={copy.pageCount} value={viewer.page_count} />
        <DetailRow label={copy.sectionCount} value={viewer.section_count} />
      </dl>
    </div>
  );
}
function Versions({
  viewer,
  onVersion,
}: {
  viewer: PolicyViewer;
  onVersion: (id: string) => void;
}) {
  const { copy, language } = useAdminCopy();
  return (
    <div className="admin-version-history">
      <h3>{copy.versionHistory}</h3>
      <p>{copy.versionHint}</p>
      {viewer.versions.map((version) => (
        <button
          type="button"
          className={`admin-version-entry ${version.id === viewer.version.id ? 'selected' : ''}`}
          key={version.id}
          onClick={() => {
            onVersion(version.id);
          }}
        >
          <span>
            <strong>
              {displayVersion(
                version.version_label,
                copy.versionLabel,
                copy.noVersion,
              )}
            </strong>
            <small>
              {formatDate(version.created_at, language)}
              {version.published_at
                ? ` · ${copy.publishedOn} ${formatDate(version.published_at, language)}`
                : ''}
              {version.source_names?.length
                ? ` · ${version.source_names.join(', ')}`
                : ''}
            </small>
          </span>
          <span>
            {version.id === viewer.policy.active_version_id
              ? copy.current
              : localizedStatus(statusLabel(version.status), copy)}
          </span>
          <ChevronDown size={16} />
        </button>
      ))}
    </div>
  );
}
export default function AdminPolicyDetailPage() {
  const { copy } = useAdminCopy();
  const queryClient = useQueryClient();
  const { policyId = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const versionId = params.get('version');
  const [tab, setTab] = useState<Tab>('Content');
  const viewer = useQuery({
    queryKey: ['admin-policy-viewer', policyId, versionId],
    queryFn: () =>
      apiRequest(
        `/admin/policies/${encodeURIComponent(policyId)}/viewer${versionId ? `?version_id=${encodeURIComponent(versionId)}` : ''}`,
        viewerSchema,
      ),
    enabled: !!policyId,
  });
  const profile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });
  const canRunTechnicalWorkflow =
    profile.data?.application_roles.includes('system_admin');
  const archive = useMutation({
    mutationFn: () =>
      apiRequest(
        `/admin/policies/${encodeURIComponent(policyId)}/deactivate`,
        policySchema,
        { method: 'POST' },
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['admin-policies'] }),
        queryClient.invalidateQueries({
          queryKey: ['admin-policy-viewer', policyId],
        }),
      ]);
    },
  });
  function selectVersion(id: string) {
    setParams(
      id === viewer.data?.policy.active_version_id ? {} : { version: id },
    );
    setTab('Content');
  }
  if (viewer.isPending)
    return (
      <div
        className="admin-content admin-detail-skeleton"
        aria-label={copy.loadingSops}
      >
        <div className="skeleton" />
        <div className="skeleton" />
        <div className="admin-detail-skeleton-body">
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      </div>
    );
  if (viewer.isError)
    return (
      <div className="admin-content">
        <Link className="admin-back" to="/admin/policies">
          <ArrowLeft size={17} /> {copy.navLibrary}
        </Link>
        <ErrorState
          title={
            viewer.error instanceof ApiError && viewer.error.status === 404
              ? copy.sopUnavailable
              : copy.sopCouldNotOpen
          }
          detail={copy.sopUnavailableDetail}
        />
      </div>
    );
  const data = viewer.data;
  const status = documentStatus(
    data.version.status,
    data.sources.map((source) => source.status),
    data.policy.status,
  );
  const isCurrent = data.version.id === data.policy.active_version_id;
  const reviewSource = data.sources.find(
    (source) =>
      source.original_allowed &&
      (source.status === 'review_required' || source.status === 'failed'),
  );
  const fullDocumentManageable = data.sources.every(
    (source) => source.original_allowed,
  );
  return (
    <section className="admin-content admin-policy-detail">
      <Link className="admin-back" to="/admin/policies">
        <ArrowLeft size={17} /> {copy.navLibrary}
      </Link>
      <header className="admin-policy-header">
        <div>
          <span className="eyebrow">{copy.organizationalSop}</span>
          <h2>{data.policy.title}</h2>
          <p>
            <FileText size={15} />{' '}
            {data.sources.map((source) => source.file_name).join(', ') ||
              copy.noSource}
          </p>
        </div>
        <div className="admin-policy-header-side">
          <span
            className={`status-text status-text--${status.toLowerCase().replaceAll(' ', '-')}`}
          >
            {localizedStatus(status, copy)}
          </span>
          <strong>
            {displayVersion(
              data.version.version_label,
              copy.versionLabel,
              copy.noVersion,
            )}
            {isCurrent && ` · ${copy.current}`}
          </strong>
        </div>
      </header>
      {status === 'Failed' && (
        <div className="admin-failed-banner">
          {copy.failedHelp}{' '}
          {reviewSource ? (
            <Link to={`/admin/review/${reviewSource.id}`}>
              {copy.reviewSource} →
            </Link>
          ) : (
            copy.inspectSource
          )}
        </div>
      )}
      <div className="admin-policy-commandbar">
        <nav className="admin-document-tabs" aria-label={copy.sopContent}>
          {tabs.map((item) => (
            <button
              key={item}
              type="button"
              className={tab === item ? 'selected' : ''}
              onClick={() => {
                setTab(item);
              }}
              aria-current={tab === item ? 'page' : undefined}
            >
              {item === 'Content' ? copy.content : copy.original}
            </button>
          ))}
        </nav>
        <div className="admin-policy-actions">
          {reviewSource && (
            <Link to={`/admin/review/${reviewSource.id}`}>
              {copy.reviewExtraction}
            </Link>
          )}
          {fullDocumentManageable && canRunTechnicalWorkflow && (
            <Link to={`/admin/workflow/${data.policy.id}`}>
              {copy.versionWorkflow}
            </Link>
          )}
          {canRunTechnicalWorkflow && data.policy.status === 'active' && (
            <button
              type="button"
              className="admin-action-link admin-action-link--danger"
              disabled={archive.isPending}
              onClick={() => {
                if (window.confirm(copy.archiveConfirm)) archive.mutate();
              }}
            >
              <Archive size={15} />
              {archive.isPending ? copy.archivingPolicy : copy.archivePolicy}
            </button>
          )}
        </div>
      </div>
      {archive.isError && (
        <div className="admin-failed-banner" role="alert">
          {archive.error instanceof Error
            ? archive.error.message
            : copy.libraryError}
        </div>
      )}
      <div className="admin-viewer-surface surface">
        {tab === 'Content' && (
          <AdminCanonicalReader
            key={data.version.id}
            viewer={data}
            details={<Details viewer={data} />}
          />
        )}
        {tab === 'Original Document' && (
          <AdminOriginalDocument sources={data.sources} />
        )}
      </div>
      <details className="admin-version-disclosure surface">
        <summary>
          <span>
            <History size={18} /> {copy.versionHistory}
          </span>
          <span>{data.versions.length}</span>
        </summary>
        <Versions viewer={data} onVersion={selectVersion} />
      </details>
    </section>
  );
}
