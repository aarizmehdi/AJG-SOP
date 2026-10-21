import hashlib
import re
from uuid import uuid4

from packages.contracts.access import UNRESTRICTED_SCOPE, AccessScope
from packages.contracts.canonical import (
    BlockKind,
    CanonicalBlock,
    CanonicalListItem,
    CanonicalSection,
    CanonicalSOP,
    CanonicalTable,
    CanonicalTableCell,
    SectionContentRole,
    SourceLocator,
)
from packages.contracts.source import SourceDocument
from services.ingestion.extractors.base import RawBlock, RawBlockKind, RawDocumentResult


class Canonicalizer:
    """Converts application-owned raw blocks into the first-class canonical SOP schema."""

    def canonicalize(
        self,
        source: SourceDocument,
        raw: RawDocumentResult,
        access: AccessScope = UNRESTRICTED_SCOPE,
    ) -> CanonicalSOP:
        sections: list[CanonicalSection] = []
        heading_stack: list[tuple[int, str, str]] = []
        current_heading = raw.title
        current_level = 1
        current_id = f"section-{uuid4().hex[:12]}"
        blocks: list[RawBlock] = []
        current_source: SourceLocator | None = None
        stable_key_counts: dict[str, int] = {}

        def flush(*, preserve_parent: bool = False) -> None:
            nonlocal blocks, current_id
            if not blocks and not preserve_parent:
                return
            path = tuple(item[1] for item in heading_stack) or (current_heading,)
            known_ids = {section.id for section in sections}
            parent_id = next(
                (item[2] for item in reversed(heading_stack[:-1]) if item[2] in known_ids), None
            )
            canonical_blocks = self._blocks(source.id, blocks)
            content = "\n".join(self.block_text(block) for block in canonical_blocks)
            policy_number = self._policy_number(current_heading) or next(
                (
                    number
                    for _, heading, _ in reversed(heading_stack)
                    if (number := self._policy_number(heading))
                ),
                None,
            )
            base_key = self._stable_key(path)
            occurrence = stable_key_counts.get(base_key, 0) + 1
            stable_key_counts[base_key] = occurrence
            content_role = (
                SectionContentRole.SOURCE_ANNOTATION
                if any(
                    heading.casefold().startswith("handwritten source annotation")
                    for _, heading, _ in heading_stack
                )
                else SectionContentRole.POLICY
            )
            sections.append(
                CanonicalSection(
                    id=current_id,
                    stable_key=base_key
                    if occurrence == 1
                    else f"{base_key}/occurrence-{occurrence}",
                    policy_number=policy_number,
                    chapter=path[0] if len(path) > 1 else None,
                    heading=current_heading,
                    content_role=content_role,
                    heading_level=current_level,
                    parent_section_id=parent_id,
                    heading_path=path,
                    blocks=canonical_blocks,
                    access=access,
                    source=(
                        self._section_locator(source.id, canonical_blocks)
                        if canonical_blocks
                        else current_source or SourceLocator(source_document_id=source.id)
                    ),
                    content_hash=self.content_hash(content, content_role),
                )
            )
            blocks = []

        for raw_block in raw.blocks:
            if raw_block.kind is RawBlockKind.HEADING:
                # Keep real policy/subsection parents even when their first
                # content is another heading. Otherwise navigation points at a
                # nonexistent parent and similarly titled policies can collapse.
                flush(
                    preserve_parent=bool(
                        heading_stack
                        and current_level > 1
                        and (raw_block.level or 1) > current_level
                    )
                )
                current_heading = raw_block.text
                current_level = raw_block.level or 1
                current_id = f"section-{uuid4().hex[:12]}"
                current_source = self._locator(source.id, raw_block)
                while heading_stack and heading_stack[-1][0] >= current_level:
                    heading_stack.pop()
                heading_stack.append((current_level, current_heading, current_id))
            else:
                blocks.append(raw_block)
        flush()
        explicit_numbers = {
            section.policy_number.casefold()
            for section in sections
            if section.policy_number
            and re.match(r"^(?:SOP|Policy)\b", section.policy_number, re.IGNORECASE)
        }
        document_number = (
            None
            if len(explicit_numbers) > 1
            else next(
                (
                    section.policy_number
                    for section in sections
                    if section.policy_number
                    and section.policy_number.casefold() in explicit_numbers
                ),
                raw.policy_number,
            )
        )
        return CanonicalSOP(
            id=f"canonical-{uuid4().hex[:12]}",
            organization_id=source.organization_id,
            policy_id=source.policy_id,
            version_id=source.version_id,
            source_document_ids=(source.id,),
            title=raw.title,
            policy_number=document_number,
            effective_date=raw.effective_date,
            sections=sections,
        )

    @staticmethod
    def _locator(source_id: str, block: RawBlock) -> SourceLocator:
        return SourceLocator(
            source_document_id=source_id,
            page_start=block.page,
            page_end=block.page,
            bounding_boxes=block.bounding_boxes,
            sheet_name=block.sheet_name,
            cell_range=block.cell_range,
            block_anchor=block.block_anchor,
            text_start=block.text_start,
            text_end=block.text_end,
        )

    def _blocks(self, source_id: str, raw_blocks: list[RawBlock]) -> list[CanonicalBlock]:
        result: list[CanonicalBlock] = []
        pending_list: list[CanonicalListItem] = []
        pending_kind: BlockKind | None = None
        level_stack: list[CanonicalListItem] = []
        for index, raw in enumerate(raw_blocks):
            if raw.kind is RawBlockKind.LIST_ITEM:
                kind = (
                    BlockKind.ORDERED_LIST
                    if raw.marker and raw.marker not in {"-", "*", "+", "•"}
                    else BlockKind.UNORDERED_LIST
                )
                level = raw.level or 0
                if pending_list and level == 0 and kind is not pending_kind:
                    result.append(self._list_block(source_id, pending_kind, pending_list, index))
                    pending_list = []
                    level_stack = []
                if not pending_list:
                    pending_kind = kind
                item = CanonicalListItem(
                    text=raw.text,
                    level=level,
                    marker=raw.marker,
                    source=self._locator(source_id, raw),
                )
                while level_stack and level_stack[-1].level >= level:
                    level_stack.pop()
                if level_stack:
                    level_stack[-1].children.append(item)
                else:
                    pending_list.append(item)
                level_stack.append(item)
                continue
            if pending_list:
                result.append(self._list_block(source_id, pending_kind, pending_list, index))
                pending_list = []
                pending_kind = None
                level_stack = []
            if raw.kind is RawBlockKind.TABLE:
                locator = self._locator(source_id, raw)
                table = CanonicalTable(
                    cells=[
                        CanonicalTableCell(
                            row=cell.row,
                            column=cell.column,
                            text=cell.text,
                            row_span=cell.row_span,
                            column_span=cell.column_span,
                            is_header=cell.is_header,
                            source=SourceLocator(
                                source_document_id=source_id,
                                page_start=cell.page,
                                page_end=cell.page,
                                bounding_boxes=cell.bounding_boxes,
                                text_start=cell.text_start,
                                text_end=cell.text_end,
                                sheet_name=cell.sheet_name,
                                cell_range=cell.cell_reference,
                                block_anchor=raw.block_anchor,
                            ),
                        )
                        for cell in raw.table_cells
                    ],
                    source=locator,
                )
                result.append(
                    CanonicalBlock(
                        id=f"block-{uuid4().hex[:12]}",
                        kind=BlockKind.TABLE,
                        table=table,
                        source=locator,
                    )
                )
            else:
                result.append(
                    CanonicalBlock(
                        id=f"block-{uuid4().hex[:12]}",
                        kind=BlockKind.PARAGRAPH,
                        text=raw.text,
                        source=self._locator(source_id, raw),
                    )
                )
        if pending_list:
            result.append(self._list_block(source_id, pending_kind, pending_list, len(raw_blocks)))
        return result

    @staticmethod
    def _list_block(
        source_id: str,
        kind: BlockKind | None,
        items: list[CanonicalListItem],
        index: int,
    ) -> CanonicalBlock:
        return CanonicalBlock(
            id=f"block-list-{index}-{uuid4().hex[:6]}",
            kind=kind or BlockKind.UNORDERED_LIST,
            list_items=items,
            source=items[0].source if items else SourceLocator(source_document_id=source_id),
        )

    @staticmethod
    def content_signature(blocks: list[CanonicalBlock]) -> tuple[object, ...]:
        """Compare source structure without version-specific IDs or coordinates."""

        def item_signature(item: CanonicalListItem) -> tuple[object, ...]:
            return (item.text, item.level, item.marker, tuple(map(item_signature, item.children)))

        return tuple(
            (
                block.kind,
                block.text,
                tuple(map(item_signature, block.list_items)),
                block.table.caption if block.table else None,
                tuple(
                    (c.row, c.column, c.text, c.row_span, c.column_span, c.is_header)
                    for c in block.table.cells
                )
                if block.table
                else (),
            )
            for block in blocks
        )

    @staticmethod
    def content_hash(content: str, role: SectionContentRole = SectionContentRole.POLICY) -> str:
        # Keep existing policy hashes compatible, while role changes remain
        # visible to version diffing instead of silently changing rule evidence.
        material = content if role is SectionContentRole.POLICY else f"{role.value}\n{content}"
        return hashlib.sha256(material.encode()).hexdigest()

    @staticmethod
    def block_text(block: CanonicalBlock) -> str:
        if block.text:
            return block.text
        if block.list_items:
            return "\n".join(Canonicalizer._list_text(item) for item in block.list_items)
        if block.table:
            return "\n".join(cell.text for cell in block.table.cells)
        return ""

    @staticmethod
    def _list_text(item: CanonicalListItem) -> str:
        return "\n".join([item.text, *(Canonicalizer._list_text(child) for child in item.children)])

    @staticmethod
    def _section_locator(source_id: str, blocks: list[CanonicalBlock]) -> SourceLocator:
        locators = [block.source for block in blocks]

        def visit(item: CanonicalListItem) -> None:
            locators.append(item.source)
            for child in item.children:
                visit(child)

        for block in blocks:
            for item in block.list_items:
                visit(item)
            if block.table:
                locators.extend(cell.source for cell in block.table.cells)
        pages = [page for loc in locators for page in (loc.page_start, loc.page_end) if page]
        first = blocks[0].source if blocks else SourceLocator(source_document_id=source_id)
        return first.model_copy(
            update={
                "page_start": min(pages) if pages else first.page_start,
                "page_end": max(pages) if pages else first.page_end,
            }
        )

    @staticmethod
    def _policy_number(heading: str) -> str | None:
        labelled = re.search(
            r"\b((?:SOP|Policy)\s*(?:No\.?|Number|#|-)?\s*"
            r"(?=[A-Za-z0-9./-]*\d)[A-Za-z0-9][A-Za-z0-9./-]*)\b",
            heading,
            flags=re.IGNORECASE,
        )
        if labelled:
            return labelled.group(1).strip()
        match = re.match(r"^(\d+(?:\.\d+)*)(?:[.)]|\s|$)", heading)
        return match.group(1) if match else None

    @staticmethod
    def _stable_key(path: tuple[str, ...]) -> str:
        normalized = "/".join(re.sub(r"\W+", "-", item.lower()).strip("-") for item in path)
        return normalized or uuid4().hex
