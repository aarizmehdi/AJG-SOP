import { useMutation, useQuery } from '@tanstack/react-query';
import { ChevronLeft, LocateFixed, Plus, UserCheck } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { Button } from '../../components/ui/Button';
import { versionSchema } from '../../types/policy';
import { profileSchema, type Profile } from '../../types/profile';
import { canonicalSopSchema, reviewPayloadSchema } from '../../types/source';
import { useAdminCopy } from './adminCopy';
import { OriginalPreview } from './OriginalPreview';

type CanonicalSop = ReturnType<typeof canonicalSopSchema.parse>;
type SourceDocument = ReturnType<typeof reviewPayloadSchema.parse>['source'];

function ReviewEditor({
  sourceId,
  source,
  raw,
  initial,
  profile,
}: {
  sourceId: string;
  source: SourceDocument;
  raw: ReturnType<typeof reviewPayloadSchema.parse>['raw'];
  initial: CanonicalSop;
  profile: Profile;
}) {
  const { copy } = useAdminCopy();
  const [draft, setDraft] = useState(initial);
  const [versionId, setVersionId] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);
  const isSystemAdmin = profile.application_roles.includes('system_admin');
  const save = useMutation({
    mutationFn: () =>
      apiRequest(`/admin/sources/${sourceId}/review`, canonicalSopSchema, {
        method: 'PUT',
        body: JSON.stringify({ canonical: draft }),
      }),
  });
  const approve = useMutation({
    mutationFn: () =>
      apiRequest(`/admin/sources/${sourceId}/approve`, versionSchema, {
        method: 'POST',
        body: JSON.stringify({ confirmed: true }),
      }),
    onSuccess: (version) => {
      setVersionId(version.id);
    },
  });
  const prepare = useMutation({
    mutationFn: () =>
      apiRequest(
        `/admin/versions/${versionId ?? ''}/prepare-publication`,
        versionSchema,
        { method: 'POST' },
      ),
  });
  const publish = useMutation({
    mutationFn: () =>
      apiRequest(`/admin/versions/${versionId ?? ''}/publish`, versionSchema, {
        method: 'POST',
      }),
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
    itemIndex: number,
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
                        index === itemIndex ? { ...item, text } : item,
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
        <span className="pill pill--review">{copy.humanReviewRequired}</span>
      </div>
      <div className="review-grid">
        <section className="review-pane source-pane">
          <header>
            <div>
              <span className="pane-label">{copy.originalSource}</span>
              <strong>{source.file_name}</strong>
            </div>
            <span>{copy.privateLabel}</span>
          </header>
          <OriginalPreview sourceId={sourceId} source={source} raw={raw} />
          <footer>{copy.sourceLocationHint}</footer>
        </section>
        <section className="review-pane canonical-pane">
          <header>
            <div>
              <span className="pane-label">{copy.canonicalSop}</span>
              <strong>{draft.title}</strong>
            </div>
            <span>Schema 1.0</span>
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
                    document
                      .getElementById(`review-${section.id}`)
                      ?.scrollIntoView({ behavior: 'smooth', block: 'start' });
                  }}
                >
                  {section.heading}
                </button>
              ))}
            </div>
          </nav>
          <div className="canonical-editor">
            {draft.sections.map((section) => (
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
                          updatePage(section.id, Number(event.target.value));
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
                          updateText(section.id, block.id, event.target.value);
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
                        <label key={`${block.id}-${String(index)}`}>
                          {copy.item} {index + 1}
                          <input
                            value={item.text}
                            onChange={(event) => {
                              updateListItem(
                                section.id,
                                block.id,
                                index,
                                event.target.value,
                              );
                            }}
                          />
                        </label>
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
            </div>
          </div>
          <footer>
            <span className="review-status" role="status">
              {publish.isSuccess
                ? copy.statusPublished
                : prepare.isSuccess
                  ? copy.indexVerified
                  : approve.isSuccess
                    ? copy.structureApproved
                    : save.isSuccess
                      ? copy.correctionsSaved
                      : ''}
            </span>
            <Button
              variant="secondary"
              disabled={save.isPending}
              onClick={() => {
                save.mutate();
              }}
            >
              {copy.saveCorrection}
            </Button>
            {!approve.isSuccess && (
              <Button
                disabled={approve.isPending || !confirmed}
                onClick={() => {
                  approve.mutate();
                }}
              >
                {copy.submitReview}
              </Button>
            )}
            {isSystemAdmin && approve.isSuccess && !prepare.isSuccess && (
              <Button
                disabled={prepare.isPending}
                onClick={() => {
                  prepare.mutate();
                }}
              >
                {copy.prepareSearchIndex}
              </Button>
            )}
            {isSystemAdmin && prepare.isSuccess && !publish.isSuccess && (
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
      <ErrorState
        title={copy.extractionUnavailable}
        detail={copy.extractionUnavailableDetail}
      />
    );
  return (
    <ReviewEditor
      key={review.data.canonical.id}
      sourceId={sourceId}
      source={review.data.source}
      raw={review.data.raw}
      initial={review.data.canonical}
      profile={profile.data}
    />
  );
}
