import { useState, type ReactNode } from 'react';
import { ChevronDown, ChevronRight, ListTree } from 'lucide-react';
import { CanonicalDocumentRenderer } from '../../components/documents/CanonicalDocumentRenderer';
import { canonicalSectionDomId } from '../../components/documents/canonicalDocumentIds';
import type { PolicyViewer } from '../../types/policy';
import { useAdminCopy } from './adminCopy';

type Section = PolicyViewer['canonicals'][number]['sections'][number];
type Node = { section: Section; children: Node[] };

function sectionTree(sections: Section[]): Node[] {
  const nodes = new Map(
    sections.map((section) => [
      section.id,
      { section, children: [] as Node[] },
    ]),
  );
  const roots: Node[] = [];
  const levels: Node[] = [];
  for (const section of sections) {
    const node = nodes.get(section.id);
    if (!node) continue;
    const explicit = section.parent_section_id
      ? nodes.get(section.parent_section_id)
      : undefined;
    const fallback = [...levels]
      .reverse()
      .find(
        (parent) =>
          parent.section.heading_level < section.heading_level &&
          parent.section.source.source_document_id ===
            section.source.source_document_id,
      );
    const parent = explicit && explicit !== node ? explicit : fallback;
    if (parent) parent.children.push(node);
    else roots.push(node);
    while (
      levels.length &&
      (levels.at(-1)?.section.heading_level ?? 0) >= section.heading_level
    )
      levels.pop();
    levels.push(node);
  }
  return roots;
}

function TreeNode({
  node,
  selected,
  onSelect,
  copy,
}: {
  node: Node;
  selected: string;
  onSelect: (id: string) => void;
  copy: ReturnType<typeof useAdminCopy>['copy'];
}) {
  const [expanded, setExpanded] = useState(true);
  return (
    <li>
      <div className="admin-tree-row">
        {node.children.length > 0 && (
          <button
            type="button"
            className="admin-tree-toggle"
            aria-label={`${expanded ? copy.collapse : copy.expand} ${node.section.heading}`}
            aria-expanded={expanded}
            onClick={() => {
              setExpanded(!expanded);
            }}
          >
            {expanded ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
          </button>
        )}
        <button
          type="button"
          className={`admin-tree-item ${selected === node.section.id ? 'selected' : ''}`}
          onClick={() => {
            onSelect(node.section.id);
          }}
          dir="auto"
        >
          {node.section.heading}
        </button>
      </div>
      {expanded && node.children.length > 0 && (
        <ul>
          {node.children.map((child) => (
            <TreeNode
              key={child.section.id}
              node={child}
              selected={selected}
              onSelect={onSelect}
              copy={copy}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

export function AdminCanonicalReader({
  viewer,
  details,
}: {
  viewer: PolicyViewer;
  details?: ReactNode;
}) {
  const { copy } = useAdminCopy();
  const sections = viewer.canonicals.flatMap((canonical) => canonical.sections);
  const [selected, setSelected] = useState<string>(sections[0]?.id ?? '');
  const [mobileOpen, setMobileOpen] = useState(false);

  function select(id: string) {
    setSelected(id);
    setMobileOpen(false);
    document
      .getElementById(canonicalSectionDomId('admin-canonical', id))
      ?.scrollIntoView({
        behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
          ? 'auto'
          : 'smooth',
        block: 'start',
      });
  }

  if (!sections.length)
    return (
      <div className="reader-notice">
        {viewer.version.status === 'failed'
          ? copy.structuredFailed
          : copy.structuredUnavailable}
      </div>
    );

  return (
    <div className="admin-reader-layout">
      <button
        className="admin-mobile-sections"
        type="button"
        aria-expanded={mobileOpen}
        onClick={() => {
          setMobileOpen(!mobileOpen);
        }}
      >
        <ListTree size={18} /> {copy.sectionsControl} <ChevronDown size={16} />
      </button>
      <aside
        className={`admin-reader-sidebar ${mobileOpen ? 'open' : ''}`}
        aria-label={copy.sectionsControl}
      >
        <div className="admin-sidebar-heading">
          <strong>{copy.contents}</strong>
          <span>
            {sections.length}{' '}
            {sections.length === 1 ? copy.section : copy.sections}
          </span>
        </div>
        <ul className="admin-section-tree">
          {sectionTree(sections).map((node) => (
            <TreeNode
              key={node.section.id}
              node={node}
              selected={selected}
              onSelect={select}
              copy={copy}
            />
          ))}
        </ul>
      </aside>
      <article className="admin-document" aria-label={copy.sopContent}>
        <div className="admin-document-kicker">
          {copy.sopContent} · {sections.length} {copy.sections}
        </div>
        <CanonicalDocumentRenderer
          sections={sections}
          idPrefix="admin-canonical"
          sourceLabel={(section) =>
            section.source.page_start
              ? `${copy.sourcePage} ${String(section.source.page_start)}${
                  section.source.page_end &&
                  section.source.page_end !== section.source.page_start
                    ? `–${String(section.source.page_end)}`
                    : ''
                }`
              : section.source.sheet_name
                ? `${copy.sourceSheet}: ${section.source.sheet_name}${
                    section.source.cell_range
                      ? ` · ${section.source.cell_range}`
                      : ''
                  }`
                : null
          }
        />
      </article>
      {details && <aside className="admin-reader-details">{details}</aside>}
    </div>
  );
}
