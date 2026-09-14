import { useMutation, useQuery } from '@tanstack/react-query';
import { ChevronLeft, LocateFixed, Plus } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { apiRequest } from '../../api/client';
import { ErrorState } from '../../components/feedback/StatePanel';
import { RouteSkeleton } from '../../components/feedback/RouteSkeleton';
import { Button } from '../../components/ui/Button';
import { versionSchema } from '../../types/policy';
import { canonicalSopSchema, reviewPayloadSchema } from '../../types/source';
import { OriginalPreview } from './OriginalPreview';

type CanonicalSop = ReturnType<typeof canonicalSopSchema.parse>;
type SourceDocument = ReturnType<typeof reviewPayloadSchema.parse>['source'];

function ReviewEditor({
  sourceId,
  source,
  raw,
  initial,
}: {
  sourceId: string;
  source: SourceDocument;
  raw: ReturnType<typeof reviewPayloadSchema.parse>['raw'];
  initial: CanonicalSop;
}) {
  const [draft, setDraft] = useState(initial);
  const [versionId, setVersionId] = useState<string | null>(null);
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
      heading: 'New section',
      heading_path: [...basis.heading_path.slice(0, -1), 'New section'],
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
            Back to library
          </Link>
          <h2>Review extracted structure</h2>
          <p>
            Correct OCR and structure on the right. The original source remains
            unchanged.
          </p>
        </div>
        <span className="pill pill--review">Human review required</span>
      </div>
      <div className="review-grid">
        <section className="review-pane source-pane">
          <header>
            <div>
              <span className="pane-label">Original source</span>
              <strong>{source.file_name}</strong>
            </div>
            <span>Private</span>
          </header>
          <OriginalPreview sourceId={sourceId} source={source} raw={raw} />
          <footer>Source locations follow the selected canonical block.</footer>
        </section>
        <section className="review-pane canonical-pane">
          <header>
            <div>
              <span className="pane-label">Canonical SOP</span>
              <strong>{draft.title}</strong>
            </div>
            <span>Schema 1.0</span>
          </header>
          <div className="canonical-editor">
            {draft.sections.map((section) => (
              <article key={section.id} className="section-editor">
                <div className="section-path">
                  <LocateFixed />
                  {section.heading_path.join(' → ')}
                </div>
                <div className="structure-fields">
                  <label>
                    Heading
                    <input
                      value={section.heading}
                      onChange={(event) => {
                        updateHeading(section.id, event.target.value);
                      }}
                    />
                  </label>
                  <label>
                    Level
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
                      Source page
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
                      Content
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
                      <legend>{block.kind.replace('_', ' ')}</legend>
                      {block.list_items.map((item, index) => (
                        <label key={`${block.id}-${String(index)}`}>
                          Item {index + 1}
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
                      <legend>Table cells</legend>
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
                  Add section after
                </button>
              </article>
            ))}
          </div>
          <footer>
            <span className="review-status" role="status">
              {publish.isSuccess
                ? 'Published'
                : prepare.isSuccess
                  ? 'Index verified — ready to publish'
                  : approve.isSuccess
                    ? 'Structure approved'
                    : save.isSuccess
                      ? 'Corrections saved'
                      : ''}
            </span>
            <Button
              variant="secondary"
              disabled={save.isPending}
              onClick={() => {
                save.mutate();
              }}
            >
              Save correction
            </Button>
            {!approve.isSuccess && (
              <Button
                disabled={approve.isPending}
                onClick={() => {
                  approve.mutate();
                }}
              >
                Approve structure
              </Button>
            )}
            {approve.isSuccess && !prepare.isSuccess && (
              <Button
                disabled={prepare.isPending}
                onClick={() => {
                  prepare.mutate();
                }}
              >
                Prepare search index
              </Button>
            )}
            {prepare.isSuccess && !publish.isSuccess && (
              <Button
                disabled={publish.isPending}
                onClick={() => {
                  publish.mutate();
                }}
              >
                Publish
              </Button>
            )}
          </footer>
        </section>
      </div>
    </section>
  );
}

export default function ExtractionReviewPage() {
  const { sourceId = '' } = useParams();
  const review = useQuery({
    queryKey: ['source-review', sourceId],
    queryFn: () =>
      apiRequest(`/admin/sources/${sourceId}/review`, reviewPayloadSchema),
  });
  if (review.isLoading) return <RouteSkeleton />;
  if (review.isError)
    return (
      <ErrorState
        title="Review unavailable"
        detail="The source may not exist in this fixture session, or the API is offline."
      />
    );
  if (!review.data?.canonical)
    return (
      <ErrorState
        title="Extraction unavailable"
        detail="This format requires a configured parser provider before canonical review."
      />
    );
  return (
    <ReviewEditor
      key={review.data.canonical.id}
      sourceId={sourceId}
      source={review.data.source}
      raw={review.data.raw}
      initial={review.data.canonical}
    />
  );
}
