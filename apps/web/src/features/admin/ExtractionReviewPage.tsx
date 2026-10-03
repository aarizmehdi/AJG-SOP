import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  ChevronLeft,
  LocateFixed,
  PencilLine,
  Plus,
  UserCheck,
  X,
} from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { CanonicalDocumentRenderer } from '../../components/documents/CanonicalDocumentRenderer';
import { Button } from '../../components/ui/Button';
import { versionSchema } from '../../types/policy';
import { profileSchema, type Profile } from '../../types/profile';
import {
  canonicalSopSchema,
  reviewPayloadSchema,
  sourceDocumentSchema,
} from '../../types/source';
import { localizedStatus, useAdminCopy } from './adminCopy';
import { OriginalPreview } from './OriginalPreview';
import { statusLabel } from './policyPresentation';

type CanonicalSop = ReturnType<typeof canonicalSopSchema.parse>;
type SourceDocument = ReturnType<typeof reviewPayloadSchema.parse>['source'];
type ReviewListItem =
  CanonicalSop['sections'][number]['blocks'][number]['list_items'][number];

function isReviewListItem(value: unknown): value is ReviewListItem {
  return (
    typeof value === 'object' &&
    value !== null &&
    'text' in value &&
    typeof value.text === 'string' &&
    'children' in value &&
    Array.isArray(value.children)
  );
}

function editListItem(
  item: ReviewListItem,
  path: number[],
  text: string,
): ReviewListItem {
  if (!path.length) return { ...item, text };
  const [target, ...rest] = path;
  return {
    ...item,
    children: item.children.map((child, index) =>
      index === target && isReviewListItem(child)
        ? editListItem(child, rest, text)
        : child,
    ),
  };
}

function ListItemFields({
  item,
  path,
  onChange,
  label,
}: {
  item: ReviewListItem;
  path: number[];
  onChange: (path: number[], text: string) => void;
  label: string;
}) {
  return (
    <div className="nested-list-field">
      <label>
        {label} {path.map((index) => index + 1).join('.')}
        <input
          value={item.text}
          onChange={(event) => {
            onChange(path, event.target.value);
          }}
        />
      </label>
      {item.children.map((child, index) =>
        isReviewListItem(child) ? (
          <ListItemFields
            key={index}
            item={child}
            path={[...path, index]}
            onChange={onChange}
            label={label}
          />
        ) : null,
      )}
    </div>
  );
}

function ReviewEditor({
  sourceId,
  source,
  versionStatus,
  raw,
  initial,
  profile,
}: {
  sourceId: string;
  source: SourceDocument;
  versionStatus: string;
  raw: ReturnType<typeof reviewPayloadSchema.parse>['raw'];
  initial: CanonicalSop;
  profile: Profile;
}) {
  const { copy } = useAdminCopy();
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState(initial);
  const [savedCanonical, setSavedCanonical] = useState(initial);
  const [editing, setEditing] = useState(false);
  const [currentStatus, setCurrentStatus] = useState(versionStatus);
  const [selectedSectionId, setSelectedSectionId] = useState(
    initial.sections[0]?.id ?? '',
  );
  const [confirmed, setConfirmed] = useState(false);
  const isSystemAdmin = profile.application_roles.includes('system_admin');
  const isImmutable = ['published', 'superseded'].includes(currentStatus);
  const save = useMutation({
    mutationFn: () =>
      apiRequest(`/admin/sources/${sourceId}/review`, canonicalSopSchema, {
        method: 'PUT',
        body: JSON.stringify({ canonical: draft }),
      }),
    onSuccess: (canonical) => {
      setDraft(canonical);
      setSavedCanonical(canonical);
      setEditing(false);
      setCurrentStatus('extraction_review');
      setConfirmed(false);
    },
  });
  const approve = useMutation({
    mutationFn: () =>
      apiRequest(`/admin/sources/${sourceId}/approve`, versionSchema, {
        method: 'POST',
        body: JSON.stringify({ confirmed: true }),
      }),
    onSuccess: (version) => {
      setCurrentStatus(version.status);
    },
  });
  const prepare = useMutation({
    mutationFn: () =>
      apiRequest(
        `/admin/versions/${source.version_id}/prepare-publication`,
        versionSchema,
        { method: 'POST' },
      ),
    onSuccess: (version) => {
      setCurrentStatus(version.status);
    },
  });
  const publish = useMutation({
    mutationFn: () =>
      apiRequest(
        `/admin/versions/${source.version_id}/publish`,
        versionSchema,
        {
          method: 'POST',
        },
      ),
    onSuccess: (version) => {
      setCurrentStatus(version.status);
    },
  });
  const retry = useMutation({
    mutationFn: () =>
      apiRequest(`/admin/sources/${sourceId}/retry`, sourceDocumentSchema, {
        method: 'POST',
      }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: ['source-review', sourceId],
        }),
        queryClient.invalidateQueries({ queryKey: ['admin-policy-viewer'] }),
        queryClient.invalidateQueries({ queryKey: ['admin-policies'] }),
      ]);
    },
  });
  const updateHeading = (sectionId: string, heading: string) => {
    setDraft({
      ...draft,
      sections: draft.sections.map((section) =>
        section.id === sectionId
          ? {
              ...section,
              heading,
              heading_path: [...section.heading_path.slice(0, -1), heading],
            }
          : section,
      ),
    });
  };
  const updateLevel = (sectionId: string, headingLevel: number) => {
    setDraft({
      ...draft,
      sections: draft.sections.map((section) =>
        section.id === sectionId
          ? { ...section, heading_level: headingLevel }
          : section,
      ),
    });
  };
  const updateText = (sectionId: string, blockId: string, text: string) => {
    setDraft({
      ...draft,
      sections: draft.sections.map((section) =>
        section.id === sectionId
          ? {
              ...section,
              blocks: section.blocks.map((block) =>
                block.id === blockId ? { ...block, text } : block,
              ),
            }
          : section,
      ),
    });
  };
  const updateListItem = (
    sectionId: string,
    blockId: string,
    path: number[],
    text: string,
  ) => {
    setDraft({
      ...draft,
      sections: draft.sections.map((section) =>
        section.id === sectionId
          ? {
              ...section,
              blocks: section.blocks.map((block) =>
                block.id === blockId
                  ? {
                      ...block,
                      list_items: block.list_items.map((item, index) =>
                        index === path[0]
                          ? editListItem(item, path.slice(1), text)
                          : item,
                      ),
                    }
                  : block,
              ),
            }
          : section,
      ),
    });
  };
  const updateTableCell = (
    sectionId: string,
    blockId: string,
    row: number,
    column: number,
    text: string,
  ) => {
    setDraft({
      ...draft,
      sections: draft.sections.map((section) =>
        section.id === sectionId
          ? {
              ...section,
              blocks: section.blocks.map((block) =>
                block.id === blockId && block.table
                  ? {
                      ...block,
                      table: {
                        ...block.table,
                        cells: block.table.cells.map((cell) =>
                          cell.row === row && cell.column === column
                            ? { ...cell, text }
                            : cell,
                        ),
                      },
                    }
                  : block,
              ),
            }
          : section,
      ),
    });
  };
  const updatePage = (sectionId: string, page: number) => {
    setDraft({
      ...draft,
      sections: draft.sections.map((section) =>
        section.id === sectionId
          ? {
              ...section,
              source: { ...section.source, page_start: page, page_end: page },
            }
          : section,
      ),
    });
  };
  const addSection = (afterId: string) => {
    const index = draft.sections.findIndex((section) => section.id === afterId);
    const basis = draft.sections[index];
    if (!basis) return;
    const id = crypto.randomUUID();
    const section = {
      ...basis,
      id: `section-review-${id}`,
      stable_key: `${basis.stable_key}-review-${id}`,
      heading: copy.newSection,
      heading_path: [...basis.heading_path.slice(0, -1), copy.newSection],
      blocks: [],
    };
    setDraft({
      ...draft,
      sections: [
        ...draft.sections.slice(0, index + 1),
        section,
        ...draft.sections.slice(index + 1),
      ],
    });
  };
  const pages = [
    ...new Set(
      raw?.blocks.flatMap((block) => (block.page ? [block.page] : [])) ?? [],
    ),
  ].sort((a, b) => a - b);
  return (
    <section className="admin-content review-workspace">
      <div className="section-heading">
        <div>
          <Link className="back-link" to="/admin">
            <ChevronLeft />
            {copy.backToLibrary}
          </Link>
          <h2>{copy.reviewTitle}</h2>
          <p>{copy.reviewLead}</p>
        </div>
        <span className="pill pill--review">
          {localizedStatus(statusLabel(currentStatus), copy)}
        </span>
      </div>
      <div className="review-grid">
        <section className="review-pane source-pane">
          <header>
            <div>
              <span className="pane-label">{copy.originalSource}</span>
              <strong>
                {source.source_format === 'markdown' &&
                !source.structured_artifact_uri
                  ? copy.originalNeedsVerification
                  : source.file_name}
              </strong>
            </div>
            <span>{copy.privateLabel}</span>
          </header>
          <OriginalPreview
            sourceId={sourceId}
            canAttach={
              source.source_format === 'markdown' &&
              !source.structured_artifact_uri &&
              !['published', 'superseded'].includes(currentStatus)
            }
          />
          <footer>{copy.sourceLocationHint}</footer>
        </section>
        <section className="review-pane canonical-pane">
          <header>
            <div>
              <span className="pane-label">{copy.canonicalSop}</span>
              <strong>{draft.title}</strong>
            </div>
            <div className="review-pane-actions">
              <span>{editing ? copy.editCanonical : copy.readOnlyPreview}</span>
              {editing ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setDraft(savedCanonical);
                    setEditing(false);
                  }}
                >
                  <X size={15} aria-hidden="true" />
                  {copy.cancelEditing}
                </Button>
              ) : !isImmutable ? (
                <Button
                  variant="secondary"
                  onClick={() => {
                    setEditing(true);
                  }}
                >
                  <PencilLine size={15} aria-hidden="true" />
                  {copy.editCanonical}
                </Button>
              ) : null}
            </div>
          </header>
          <nav className="review-toc" aria-label={copy.structuredSopContents}>
            <strong>{copy.contents}</strong>
            <div>
              {draft.sections.map((section) => (
                <button
                  key={section.id}
                  type="button"
                  dir="auto"
                  onClick={() => {
                    setSelectedSectionId(section.id);
                    const scroller = document.querySelector(
                      '.review-canonical-preview',
                    );
                    const target = document.getElementById(
                      `review-${section.id}`,
                    );
                    if (scroller && target) {
                      const offset =
                        target.getBoundingClientRect().top -
                        scroller.getBoundingClientRect().top +
                        scroller.scrollTop;
                      scroller.scrollTo({ top: offset, behavior: 'smooth' });
                    }
                  }}
                  aria-current={
                    selectedSectionId === section.id ? 'location' : undefined
                  }
                >
                  {section.heading}
                </button>
              ))}
            </div>
          </nav>
          {editing ? (
            <div className="canonical-editor">
              {draft.sections
                .filter((section) => section.id === selectedSectionId)
                .map((section) => (
                  <article
                    key={section.id}
                    id={`review-${section.id}`}
                    className="section-editor"
                  >
                    <div className="section-path">
                      <LocateFixed />
                      {section.heading_path.join(' → ')}
                    </div>
                    <div className="structure-fields">
                      <label>
                        {copy.heading}
                        <input
                          value={section.heading}
                          onChange={(event) => {
                            updateHeading(section.id, event.target.value);
                          }}
                        />
                      </label>
                      <label>
                        {copy.level}
                        <input
                          type="number"
                          min="1"
                          max="6"
                          value={section.heading_level}
                          onChange={(event) => {
                            updateLevel(section.id, Number(event.target.value));
                          }}
                        />
                      </label>
                      {pages.length > 0 && (
                        <label>
                          {copy.sourcePage}
                          <select
                            value={section.source.page_start ?? pages[0]}
                            onChange={(event) => {
                              updatePage(
                                section.id,
                                Number(event.target.value),
                              );
                            }}
                          >
                            {pages.map((page) => (
                              <option key={page} value={page}>
                                {page}
                              </option>
                            ))}
                          </select>
                        </label>
                      )}
                    </div>
                    {section.blocks.map((block) =>
                      block.text !== null ? (
                        <label key={block.id}>
                          {copy.content}
                          <textarea
                            value={block.text}
                            rows={4}
                            onChange={(event) => {
                              updateText(
                                section.id,
                                block.id,
                                event.target.value,
                              );
                            }}
                          />
                        </label>
                      ) : block.list_items.length > 0 ? (
                        <fieldset className="structured-editor" key={block.id}>
                          <legend>
                            {block.kind === 'ordered_list'
                              ? copy.orderedList
                              : copy.unorderedList}
                          </legend>
                          {block.list_items.map((item, index) => (
                            <ListItemFields
                              key={`${block.id}-${String(index)}`}
                              item={item}
                              path={[index]}
                              label={copy.item}
                              onChange={(path, text) => {
                                updateListItem(
                                  section.id,
                                  block.id,
                                  path,
                                  text,
                                );
                              }}
                            />
                          ))}
                        </fieldset>
                      ) : block.table ? (
                        <fieldset className="structured-editor" key={block.id}>
                          <legend>{copy.tableCells}</legend>
                          {block.table.cells.map((cell) => (
                            <label
                              key={`${String(cell.row)}-${String(cell.column)}`}
                            >
                              R{cell.row + 1} C{cell.column + 1}
                              <input
                                value={cell.text}
                                onChange={(event) => {
                                  updateTableCell(
                                    section.id,
                                    block.id,
                                    cell.row,
                                    cell.column,
                                    event.target.value,
                                  );
                                }}
                              />
                            </label>
                          ))}
                        </fieldset>
                      ) : null,
                    )}
                    <button
                      className="add-section"
                      type="button"
                      onClick={() => {
                        addSection(section.id);
                      }}
                    >
                      <Plus />
                      {copy.addSectionAfter}
                    </button>
                  </article>
                ))}
            </div>
          ) : (
            <CanonicalDocumentRenderer
              sections={draft.sections}
              idPrefix="review"
              className="review-canonical-preview"
              sourceLabel={(section) =>
                section.source.page_start
                  ? `${copy.sourcePage} ${String(section.source.page_start)}`
                  : null
              }
            />
          )}
          <div className="review-identity">
            <UserCheck size={20} aria-hidden="true" />
            <div>
              <span>{copy.reviewingAs}</span>
              <strong>{profile.display_name}</strong>
              <small>
                {profile.application_roles.includes('system_admin')
                  ? copy.systemAdministrator
                  : copy.sopAdministrator}
                {profile.email ? ` · ${profile.email}` : ''}
              </small>
              {currentStatus === 'extraction_review' && (
                <label>
                  <input
                    type="checkbox"
                    checked={confirmed}
                    onChange={(event) => {
                      setConfirmed(event.target.checked);
                    }}
                  />
                  {copy.confirmCompared}
                </label>
              )}
            </div>
          </div>
          {[save, approve, prepare, publish, retry].map((operation, index) =>
            operation.isError ? (
              <p
                className="form-error review-action-error"
                role="alert"
                key={index}
              >
                {operation.error.message}
              </p>
            ) : null,
          )}
          <footer>
            <span className="review-status" role="status">
              {currentStatus === 'published'
                ? copy.statusPublished
                : currentStatus === 'ready_to_publish'
                  ? copy.indexVerified
                  : currentStatus === 'ready_for_indexing'
                    ? copy.structureApproved
                    : save.isSuccess
                      ? copy.correctionsSaved
                      : ''}
            </span>
            {editing && (
              <Button
                variant="secondary"
                disabled={save.isPending}
                onClick={() => {
                  save.mutate();
                }}
              >
                {copy.saveCorrection}
              </Button>
            )}
            {currentStatus === 'extraction_review' && !editing && (
              <Button
                disabled={approve.isPending || !confirmed}
                onClick={() => {
                  approve.mutate();
                }}
              >
                {copy.submitReview}
              </Button>
            )}
            {isSystemAdmin &&
              (currentStatus === 'ready_for_indexing' ||
                (currentStatus === 'failed' &&
                  source.status === 'approved')) && (
                <Button
                  disabled={prepare.isPending}
                  onClick={() => {
                    prepare.mutate();
                  }}
                >
                  {copy.prepareSearchIndex}
                </Button>
              )}
            {isSystemAdmin &&
              currentStatus === 'failed' &&
              source.status === 'failed' && (
                <Button
                  disabled={retry.isPending}
                  onClick={() => {
                    retry.mutate();
                  }}
                >
                  {copy.retryProcessing}
                </Button>
              )}
            {isSystemAdmin && currentStatus === 'ready_to_publish' && (
              <Button
                disabled={publish.isPending}
                onClick={() => {
                  publish.mutate();
                }}
              >
                {copy.publish}
              </Button>
            )}
          </footer>
        </section>
      </div>
    </section>
  );
}

export default function ExtractionReviewPage() {
  const { copy } = useAdminCopy();
  const queryClient = useQueryClient();
  const { sourceId = '' } = useParams();
  const review = useQuery({
    queryKey: ['source-review', sourceId],
    queryFn: () =>
      apiRequest(`/admin/sources/${sourceId}/review`, reviewPayloadSchema),
  });
  const profile = useQuery({
    queryKey: ['profile'],
    queryFn: () => apiRequest('/profile/me', profileSchema),
  });
  const retryUnavailable = useMutation({
    mutationFn: () =>
      apiRequest(`/admin/sources/${sourceId}/retry`, sourceDocumentSchema, {
        method: 'POST',
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ['source-review', sourceId],
      });
    },
  });
  if (review.isLoading || profile.isLoading) return <RouteSkeleton />;
  if (review.isError)
    return (
      <ErrorState
        title={copy.reviewUnavailable}
        detail={copy.reviewUnavailableDetail}
      />
    );
  if (!review.data?.canonical || !profile.data)
    return (
      <div className="admin-content">
        <ErrorState
          title={copy.extractionUnavailable}
          detail={copy.extractionUnavailableDetail}
        />
        {review.data?.source.status === 'failed' &&
          profile.data?.application_roles.includes('system_admin') && (
            <Button
              disabled={retryUnavailable.isPending}
              onClick={() => {
                retryUnavailable.mutate();
              }}
            >
              {copy.retryProcessing}
            </Button>
          )}
        {retryUnavailable.isError && (
          <p className="form-error" role="alert">
            {retryUnavailable.error.message}
          </p>
        )}
      </div>
    );
  return (
    <ReviewEditor
      key={`${review.data.canonical.id}-${review.data.version.status}-${review.data.source.status}-${review.data.source.original_artifact_uri}`}
      sourceId={sourceId}
      source={review.data.source}
      versionStatus={review.data.version.status}
      raw={review.data.raw}
      initial={review.data.canonical}
      profile={profile.data}
    />
  );
}
