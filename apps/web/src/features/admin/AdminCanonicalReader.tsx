import { useState, type ReactNode } from 'react';
import { ChevronDown, ChevronRight, ListTree } from 'lucide-react';
import type { PolicyViewer } from '../../types/policy';
import { useAdminCopy } from './adminCopy';

type Section = PolicyViewer['canonicals'][number]['sections'][number];
type Block = Section['blocks'][number];
type ListItem = { text: string; marker?: string | null; children?: ListItem[] };
function isListItem(value: unknown): value is ListItem {
  return (
    !!value &&
    typeof value === 'object' &&
    'text' in value &&
    typeof value.text === 'string'
  );
}
function ListItems({ items, ordered }: { items: unknown[]; ordered: boolean }) {
  const Element = ordered ? 'ol' : 'ul';
  return (
    <Element>
      {items.filter(isListItem).map((item, index) => (
        <li key={index} dir="auto">
          {item.text}
          {item.children?.length ? (
            <ListItems items={item.children} ordered={ordered} />
          ) : null}
        </li>
      ))}
    </Element>
  );
}
function Table({ table }: { table: NonNullable<Block['table']> }) {
  const rows = [...new Set(table.cells.map((cell) => cell.row))].sort(
    (a, b) => a - b,
  );
  return (
    <div className="admin-table-wrap">
      <table>
        {table.caption && <caption>{table.caption}</caption>}
        <tbody>
          {rows.map((row) => (
            <tr key={row}>
              {table.cells
                .filter((cell) => cell.row === row)
                .sort((a, b) => a.column - b.column)
                .map((cell) => {
                  const Element = cell.is_header ? 'th' : 'td';
                  return (
                    <Element
                      key={cell.column}
                      colSpan={cell.column_span}
                      rowSpan={cell.row_span}
                      dir="auto"
                    >
                      {cell.text}
                    </Element>
                  );
                })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
function ContentBlock({ block }: { block: Block }) {
  if (block.kind === 'paragraph') return <p dir="auto">{block.text}</p>;
  if (block.kind === 'ordered_list' || block.kind === 'unordered_list')
    return (
      <ListItems
        items={block.list_items}
        ordered={block.kind === 'ordered_list'}
      />
    );
  if (block.table) return <Table table={block.table} />;
  return null;
}
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
    document.getElementById(`canonical-${id}`)?.scrollIntoView({
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
        {sections.map((section) => (
          <section
            className="admin-document-section"
            id={`canonical-${section.id}`}
            key={section.id}
          >
            {section.chapter && (
              <div className="admin-document-chapter">{section.chapter}</div>
            )}
            <h2 dir="auto">{section.heading}</h2>
            {section.policy_number && (
              <span className="admin-policy-number">
                {copy.policy} {section.policy_number}
              </span>
            )}
            <div className="admin-document-body">
              {section.blocks.map((block) => (
                <ContentBlock key={block.id} block={block} />
              ))}
            </div>
            {section.source.page_start && (
              <div className="admin-page-ref">
                {copy.sourcePage} {section.source.page_start}
                {section.source.page_end &&
                section.source.page_end !== section.source.page_start
                  ? `–${String(section.source.page_end)}`
                  : ''}
              </div>
            )}
            {section.source.sheet_name && (
              <div className="admin-page-ref">
                {copy.sourceSheet}: {section.source.sheet_name}
                {section.source.cell_range
                  ? ` · ${section.source.cell_range}`
                  : ''}
              </div>
            )}
          </section>
        ))}
      </article>
      {details && <aside className="admin-reader-details">{details}</aside>}
    </div>
  );
}
