import type { ElementType, ReactNode } from 'react';
import { canonicalSectionDomId } from './canonicalDocumentIds';

export type CanonicalListItemView = {
  text: string;
  marker?: string | null;
  children?: unknown[];
};

export type CanonicalTableCellView = {
  row: number;
  column: number;
  text: string;
  row_span: number;
  column_span: number;
  is_header: boolean;
};

export type CanonicalBlockView = {
  id: string;
  kind: 'paragraph' | 'ordered_list' | 'unordered_list' | 'table';
  text?: string | null;
  list_items: unknown[];
  table?: {
    caption?: string | null;
    cells: CanonicalTableCellView[];
  } | null;
};

export type CanonicalSectionView = {
  id: string;
  heading: string;
  heading_level: number;
  parent_section_id?: string | null;
  chapter?: string | null;
  policy_number?: string | null;
  blocks: CanonicalBlockView[];
  source: {
    page_start?: number | null;
    page_end?: number | null;
    sheet_name?: string | null;
    cell_range?: string | null;
  };
};

function isListItem(value: unknown): value is CanonicalListItemView {
  return (
    !!value &&
    typeof value === 'object' &&
    'text' in value &&
    typeof value.text === 'string'
  );
}

function CanonicalList({
  items,
  ordered,
}: {
  items: unknown[];
  ordered: boolean;
}) {
  const List = ordered ? 'ol' : 'ul';
  return (
    <List>
      {items.filter(isListItem).map((item, index) => (
        <li key={`${item.text}-${String(index)}`} dir="auto">
          <span>{item.text}</span>
          {item.children?.length ? (
            <CanonicalList items={item.children} ordered={ordered} />
          ) : null}
        </li>
      ))}
    </List>
  );
}

function CanonicalTable({
  table,
}: {
  table: NonNullable<CanonicalBlockView['table']>;
}) {
  const rows = [...new Set(table.cells.map((cell) => cell.row))].sort(
    (left, right) => left - right,
  );
  return (
    <div className="canonical-table-wrap">
      <table>
        {table.caption && <caption dir="auto">{table.caption}</caption>}
        <tbody>
          {rows.map((row) => (
            <tr key={row}>
              {table.cells
                .filter((cell) => cell.row === row)
                .sort((left, right) => left.column - right.column)
                .map((cell) => {
                  const Cell = cell.is_header ? 'th' : 'td';
                  return (
                    <Cell
                      key={`${String(cell.row)}-${String(cell.column)}`}
                      colSpan={cell.column_span}
                      rowSpan={cell.row_span}
                      dir="auto"
                    >
                      {cell.text}
                    </Cell>
                  );
                })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CanonicalBlock({ block }: { block: CanonicalBlockView }) {
  if (block.kind === 'paragraph')
    return block.text ? <p dir="auto">{block.text}</p> : null;
  if (block.kind === 'ordered_list' || block.kind === 'unordered_list')
    return (
      <CanonicalList
        items={block.list_items}
        ordered={block.kind === 'ordered_list'}
      />
    );
  if (block.table) return <CanonicalTable table={block.table} />;
  return null;
}

export function CanonicalDocumentRenderer({
  sections,
  idPrefix = 'canonical',
  highlightedSectionId,
  sourceLabel,
  className = '',
  sectionActions,
}: {
  sections: CanonicalSectionView[];
  idPrefix?: string;
  highlightedSectionId?: string | null;
  sourceLabel?: (section: CanonicalSectionView) => ReactNode;
  className?: string;
  sectionActions?: (section: CanonicalSectionView) => ReactNode;
}) {
  return (
    <div className={`canonical-document ${className}`.trim()}>
      {sections.map((section) => {
        const level = Math.min(6, Math.max(2, section.heading_level + 1));
        const Heading = `h${String(level)}` as ElementType;
        const highlighted = section.id === highlightedSectionId;
        return (
          <section
            id={canonicalSectionDomId(idPrefix, section.id)}
            className={`canonical-section${highlighted ? ' canonical-section--focused' : ''}`}
            key={section.id}
            tabIndex={highlighted ? -1 : undefined}
            aria-label={section.heading}
          >
            {section.chapter && (
              <div className="canonical-chapter" dir="auto">
                {section.chapter}
              </div>
            )}
            <div className="canonical-section-heading">
              <div>
                {section.policy_number && (
                  <span className="canonical-policy-number">
                    {section.policy_number}
                  </span>
                )}
                <Heading dir="auto">{section.heading}</Heading>
              </div>
              {sectionActions?.(section)}
            </div>
            <div className="canonical-blocks">
              {section.blocks.map((block) => (
                <CanonicalBlock key={block.id} block={block} />
              ))}
            </div>
            {sourceLabel && (
              <div className="canonical-source-reference">
                {sourceLabel(section)}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
