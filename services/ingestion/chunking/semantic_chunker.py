from abc import ABC, abstractmethod

import structlog

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


def _build_table_grid(table: CanonicalTable) -> list[list[str]]:
    if not table.cells:
        return []

    max_row = max(c.row + c.row_span - 1 for c in table.cells)
    max_col = max(c.column + c.column_span - 1 for c in table.cells)

    grid = [["" for _ in range(max_col + 1)] for _ in range(max_row + 1)]
    for cell in table.cells:
        for r in range(cell.row, cell.row + cell.row_span):
            for c in range(cell.column, cell.column + cell.column_span):
                grid[r][c] = cell.text.replace("\n", " ").replace("|", "\\|")
    return grid


def serialize_table(table: CanonicalTable) -> list[str]:
    grid = _build_table_grid(table)
    if not grid:
        return []

    lines = []
    if table.caption:
        lines.append(f"**{table.caption}**")

    for i, row in enumerate(grid):
        lines.append("| " + " | ".join(row) + " |")
        if i == 0:
            lines.append("|" + "|".join(["---"] * len(row)) + "|")

    return lines


class Chunker(ABC):
    @abstractmethod
    def chunk(self, document: CanonicalSOP, publication_status: str) -> list[RetrievalChunk]:
        raise NotImplementedError


class SemanticChunker(Chunker):
    """Chunks documents preserving sections, heading paths, and access metadata."""

    MAX_WORDS = 350

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Conservative dependency-free token estimate for English SOP text.

        Uses max(words * 1.35, characters / 3.8) to account for subwords,
        markdown table pipes, short numeric cells, and punctuation without
        requiring a downloaded tokenizer.
        """
        words = len(text.split())
        chars = len(text)
        return max(int(words * 1.35 + 0.999), int(chars / 3.8 + 0.999))

    def chunk(self, document: CanonicalSOP, publication_status: str) -> list[RetrievalChunk]:
        chunks: list[RetrievalChunk] = []
        for section in document.sections:
            chunks.extend(self._chunk_section(document, section, publication_status))
        return chunks

    def _split_oversized_table_row(
        self,
        headers: list[str],
        row_cells: list[str],
        caption: str | None,
        heading: str,
    ) -> list[list[str]]:
        num_cols = len(headers)
        context_cell = row_cells[0] if num_cols > 0 else ""

        header_lines: list[str] = []
        if caption:
            header_lines.append(f"**{caption}**")
        header_lines.append("| " + " | ".join(headers) + " |")
        header_lines.append("|" + "|".join(["---"] * num_cols) + "|")

        parts: list[list[str]] = []

        if num_cols <= 1:
            words = context_cell.split()
            for i in range(0, len(words), self.MAX_WORDS):
                seg = " ".join(words[i : i + self.MAX_WORDS])
                parts.append([*header_lines, f"| {seg} |"])
            return parts

        if len(context_cell.split()) > self.MAX_WORDS:
            structlog.get_logger().warning(
                "oversized_table_row_header_context_exceeds_limit",
                heading=heading,
                caption=caption,
                context_words=len(context_cell.split()),
                limit=self.MAX_WORDS,
            )

        def row_line_for(col_dict: dict[int, str]) -> str:
            cells = [context_cell]
            for c in range(1, num_cols):
                cells.append(col_dict.get(c, ""))
            return "| " + " | ".join(cells) + " |"

        def row_words(col_dict: dict[int, str]) -> int:
            return len(row_line_for(col_dict).split())

        current_cols: dict[int, str] = {}

        for c in range(1, num_cols):
            cell_text = row_cells[c]
            if not cell_text:
                continue

            cell_words = len(cell_text.split())

            if cell_words > self.MAX_WORDS:
                if current_cols:
                    parts.append([*header_lines, row_line_for(current_cols)])
                    current_cols = {}

                words = cell_text.split()
                for i in range(0, len(words), self.MAX_WORDS):
                    seg = " ".join(words[i : i + self.MAX_WORDS])
                    parts.append([*header_lines, row_line_for({c: seg})])
            else:
                test_cols = dict(current_cols)
                test_cols[c] = cell_text
                if row_words(test_cols) <= self.MAX_WORDS or not current_cols:
                    current_cols[c] = cell_text
                else:
                    parts.append([*header_lines, row_line_for(current_cols)])
                    current_cols = {c: cell_text}

        if current_cols:
            parts.append([*header_lines, row_line_for(current_cols)])

        if not parts:
            parts.append([*header_lines, row_line_for({})])

        return parts

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
                grid = _build_table_grid(block.table)  # type: ignore
                if not grid:
                    continue

                caption = block.table.caption if block.table else None
                grid_headers = grid[0]

                header_lines: list[str] = []
                if caption:
                    header_lines.append(f"**{caption}**")
                header_lines.append("| " + " | ".join(grid_headers) + " |")
                header_lines.append("|" + "|".join(["---"] * len(grid_headers)) + "|")

                data_rows = grid[1:]
                if not data_rows:
                    current_text.extend(header_lines)
                    current_words += sum(len(line.split()) for line in header_lines)
                    continue

                temp_table_lines = list(header_lines)
                table_words_so_far = 0

                for row_cells in data_rows:
                    line = "| " + " | ".join(row_cells) + " |"
                    line_words = len(line.split())

                    if line_words > self.MAX_WORDS:
                        if table_words_so_far > 0:
                            current_text.extend(temp_table_lines)
                            current_words += table_words_so_far
                        if current_text:
                            flush()
                        temp_table_lines = list(header_lines)
                        table_words_so_far = 0

                        part_lines_list = self._split_oversized_table_row(
                            grid_headers,
                            row_cells,
                            caption=caption,
                            heading=heading,
                        )
                        for part_lines in part_lines_list:
                            current_text = list(part_lines)
                            current_words = sum(len(pl.split()) for pl in part_lines)
                            flush()

                        temp_table_lines = list(header_lines)
                        table_words_so_far = 0
                        continue

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
