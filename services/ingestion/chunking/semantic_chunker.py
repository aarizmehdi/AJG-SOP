from abc import ABC, abstractmethod

from packages.contracts.canonical import (
    BlockKind,
    CanonicalBlock,
    CanonicalListItem,
    CanonicalSOP,
    CanonicalTable,
    RetrievalChunk,
)


def serialize_list(items: list[CanonicalListItem], parent_text: str = "") -> list[str]:
    result = []
    for item in items:
        current = f"{parent_text} > {item.text}" if parent_text else item.text
        result.append(current)
        if item.children:
            result.extend(serialize_list(item.children, current))
    return result

def serialize_table(table: CanonicalTable) -> list[str]:
    grid = {}
    for cell in table.cells:
        for r in range(cell.row, cell.row + cell.row_span):
            for c in range(cell.column, cell.column + cell.column_span):
                grid[(r, c)] = cell

    lines = []
    table_heading = table.caption or "Table"

    for cell in table.cells:
        if cell.is_header:
            continue

        row_header = grid.get((cell.row, 0))
        col_header = grid.get((0, cell.column))

        r_text = row_header.text if row_header and row_header.is_header and row_header != cell else None  # noqa: E501
        c_text = col_header.text if col_header and col_header.is_header and col_header != cell else None  # noqa: E501

        parts = [f"[{table_heading}]"]
        if r_text:
            parts.append(r_text)
        if c_text:
            parts.append(f"{c_text}: {cell.text}")
        else:
            parts.append(cell.text)

        lines.append(" -> ".join(parts))

    if not lines:
        return [cell.text for cell in table.cells]
    
    # Deduplicate in case of spans
    return list(dict.fromkeys(lines))


class Chunker(ABC):
    @abstractmethod
    def chunk(self, document: CanonicalSOP, publication_status: str) -> list[RetrievalChunk]:
        raise NotImplementedError


class SemanticChunker(Chunker):
    """Chunks documents preserving sections, heading paths, and access metadata."""

    MAX_WORDS = 350

    def chunk(self, document: CanonicalSOP, publication_status: str) -> list[RetrievalChunk]:
        chunks: list[RetrievalChunk] = []
        for section in document.sections:
            chunks.extend(self._chunk_section(document, section, publication_status))
        return chunks

    def _chunk_section(self, document, section, publication_status) -> list[RetrievalChunk]:
        chunks = []
        current_text = []
        current_words = 0
        chunk_index = 0

        heading = " > ".join(section.heading_path)

        def flush():
            nonlocal current_text, current_words, chunk_index
            if not current_text:
                return

            text = f"{heading}\n" + "\n".join(current_text)
            chunks.append(
                RetrievalChunk(
                    id=f"{document.version_id}:{section.id}:{chunk_index}",
                    organization_id=document.organization_id,
                    policy_id=document.policy_id,
                    version_id=document.version_id,
                    source_document_id=section.source.source_document_id,
                    section_id=section.id,
                    parent_section_id=section.parent_section_id,
                    heading_path=section.heading_path,
                    policy_number=section.policy_number,
                    text=text,
                    access=section.access,
                    source=section.source,
                    chunk_index=chunk_index,
                    publication_status=publication_status,
                )
            )
            chunk_index += 1
            current_text = []
            current_words = 0

        for block in section.blocks:
            block_text = self._serialize_block(block)
            block_words = len(block_text.split())

            if current_words + block_words > self.MAX_WORDS and current_words > 0:
                flush()

            if block_words > self.MAX_WORDS:
                # Oversized section fallback
                words = block_text.split()
                for i in range(0, len(words), self.MAX_WORDS):
                    segment = " ".join(words[i : i + self.MAX_WORDS])
                    current_text.append(segment)
                    flush()
            else:
                current_text.append(block_text)
                current_words += block_words

        flush()
        return chunks

    def _serialize_block(self, block: CanonicalBlock) -> str:
        if block.text:
            return block.text
        elif block.list_items:
            return "\n".join(serialize_list(block.list_items))
        elif block.kind is BlockKind.TABLE and block.table:
            return "\n".join(serialize_table(block.table))
        return ""


SectionAwareFixtureChunker = SemanticChunker

