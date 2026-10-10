from abc import ABC, abstractmethod

from packages.contracts.canonical import (
    BlockKind,
    CanonicalBlock,
    CanonicalListItem,
    CanonicalSection,
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
    if not table.cells:
        return []

    max_row = max(c.row + c.row_span - 1 for c in table.cells)
    max_col = max(c.column + c.column_span - 1 for c in table.cells)

    grid = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    for cell in table.cells:
        for r in range(cell.row, cell.row + cell.row_span):
            for c in range(cell.column, cell.column + cell.column_span):
                grid[r][c] = cell.text.replace("\n", " ").replace("|", "\\|")

    lines = []
    if table.caption:
        lines.append(f"**{table.caption}**")

    for i, row in enumerate(grid):
        lines.append("| " + " | ".join(row) + " |")
        if i == 0:
            lines.append("|" + "|".join(["---"] * (max_col + 1)) + "|")

    return lines


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

    def _chunk_section(
        self, document: CanonicalSOP, section: CanonicalSection, publication_status: str
    ) -> list[RetrievalChunk]:  # noqa: E501
        chunks: list[RetrievalChunk] = []
        current_text: list[str] = []
        current_words = 0
        chunk_index = 0

        heading = " > ".join(section.heading_path)

        def flush() -> None:
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
            is_table = block.kind is BlockKind.TABLE and block.table is not None

            if is_table:
                table_lines = serialize_table(block.table)  # type: ignore
                header_count = 3 if block.table and block.table.caption else 2
                header_lines = table_lines[:header_count]
                data_lines = table_lines[header_count:]

                # Start with headers if we process data lines
                table_words_so_far = 0
                temp_table_lines = list(header_lines)

                for line in data_lines:
                    line_words = len(line.split())
                    if current_words + table_words_so_far + line_words > self.MAX_WORDS and (
                        current_words > 0 or table_words_so_far > 0
                    ):
                        if table_words_so_far > 0:
                            current_text.extend(temp_table_lines)
                            current_words += table_words_so_far
                        flush()
                        temp_table_lines = list(header_lines)
                        table_words_so_far = 0

                    temp_table_lines.append(line)
                    table_words_so_far += line_words

                if table_words_so_far > 0:
                    current_text.extend(temp_table_lines)
                    current_words += table_words_so_far

                continue

            block_text = self._serialize_block(block)
            block_words = len(block_text.split())

            if current_words + block_words > self.MAX_WORDS and current_words > 0:
                flush()

            if block_words > self.MAX_WORDS:
                # Oversized section fallback: split by lines to preserve table/list integrity
                for line in block_text.split("\n"):
                    line_words = len(line.split())
                    if current_words + line_words > self.MAX_WORDS and current_words > 0:
                        flush()

                    if line_words > self.MAX_WORDS:
                        words = line.split()
                        for i in range(0, len(words), self.MAX_WORDS):
                            segment = " ".join(words[i : i + self.MAX_WORDS])
                            current_text.append(segment)
                            flush()
                    else:
                        current_text.append(line)
                        current_words += line_words
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
