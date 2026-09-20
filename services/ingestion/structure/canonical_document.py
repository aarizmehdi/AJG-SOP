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

        def flush() -> None:
            nonlocal blocks, current_id
            if not blocks:
                return
            path = tuple(item[1] for item in heading_stack) or (current_heading,)
            parent_id = heading_stack[-2][2] if len(heading_stack) > 1 else None
            canonical_blocks = self._blocks(source.id, blocks)
            content = "\n".join(self._block_text(block) for block in canonical_blocks)
            policy_number = self._policy_number(current_heading)
            sections.append(
                CanonicalSection(
                    id=current_id,
                    stable_key=self._stable_key(path),
                    policy_number=policy_number,
                    chapter=path[0] if len(path) > 1 else None,
                    heading=current_heading,
                    heading_level=current_level,
                    parent_section_id=parent_id,
                    heading_path=path,
                    blocks=canonical_blocks,
                    access=access,
                    source=self._section_locator(source.id, canonical_blocks),
                    content_hash=hashlib.sha256(content.encode()).hexdigest(),
                )
            )
            blocks = []

        for raw_block in raw.blocks:
            if raw_block.kind is RawBlockKind.HEADING:
                flush()
                current_heading = raw_block.text
                current_level = raw_block.level or 1
                current_id = f"section-{uuid4().hex[:12]}"
                while heading_stack and heading_stack[-1][0] >= current_level:
                    heading_stack.pop()
                heading_stack.append((current_level, current_heading, current_id))
            else:
                blocks.append(raw_block)
        flush()
        return CanonicalSOP(
            id=f"canonical-{uuid4().hex[:12]}",
            organization_id=source.organization_id,
            policy_id=source.policy_id,
            version_id=source.version_id,
            source_document_ids=(source.id,),
            title=raw.title,
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
        for index, raw in enumerate(raw_blocks):
            if raw.kind is RawBlockKind.LIST_ITEM:
                kind = (
                    BlockKind.ORDERED_LIST
                    if raw.marker and raw.marker[0].isdigit()
                    else BlockKind.UNORDERED_LIST
                )
                if pending_list and kind is not pending_kind:
                    result.append(self._list_block(source_id, pending_kind, pending_list, index))
                    pending_list = []
                pending_kind = kind
                pending_list.append(
                    CanonicalListItem(
                        text=raw.text,
                        level=raw.level or 0,
                        marker=raw.marker,
                        source=self._locator(source_id, raw),
                    )
                )
                continue
            if pending_list:
                result.append(self._list_block(source_id, pending_kind, pending_list, index))
                pending_list = []
                pending_kind = None
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
    def _block_text(block: CanonicalBlock) -> str:
        if block.text:
            return block.text
        if block.list_items:
            return "\n".join(item.text for item in block.list_items)
        if block.table:
            return "\n".join(cell.text for cell in block.table.cells)
        return ""

    @staticmethod
    def _section_locator(source_id: str, blocks: list[CanonicalBlock]) -> SourceLocator:
        pages = [block.source.page_start for block in blocks if block.source.page_start]
        first = blocks[0].source if blocks else SourceLocator(source_document_id=source_id)
        return first.model_copy(
            update={
                "page_start": min(pages) if pages else first.page_start,
                "page_end": max(pages) if pages else first.page_end,
            }
        )

    @staticmethod
    def _policy_number(heading: str) -> str | None:
        match = re.match(r"^([A-Z]{1,8}[- ]?\d+(?:\.\d+)*|\d+(?:\.\d+)+)\b", heading)
        return match.group(1) if match else None

    @staticmethod
    def _stable_key(path: tuple[str, ...]) -> str:
        normalized = "/".join(re.sub(r"\W+", "-", item.lower()).strip("-") for item in path)
        return normalized or uuid4().hex
