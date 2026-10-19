import importlib
import os
import re
from abc import ABC, abstractmethod
from typing import Any

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
    """Token-aware semantic chunker preserving sections, heading paths, and access metadata."""

    MAX_WORDS = 350
    SOFT_TARGET_TOKENS = 480
    HARD_MAX_TOKENS = 507
    PASSAGE_PREFIX = "passage: "
    PREFIX_OVERHEAD_TOKENS = 4  # <s> + </s> + passage + :

    def __init__(self, tokenizer: Any | None = None) -> None:
        self._tokenizer = tokenizer
        if self._tokenizer is None:
            self._tokenizer = self._resolve_tokenizer()

    @staticmethod
    def _resolve_tokenizer() -> Any | None:
        """Optionally resolve a local tokenizer if configured via environment.

        Safe default is None. No hard-coded paths. tokenizers is lazily imported
        only when an explicit valid file path is supplied.
        """
        path = os.environ.get("E5_TOKENIZER_PATH")
        if not path or not os.path.exists(path):
            return None
        try:
            tokenizers_module = importlib.import_module("tokenizers")
            Tokenizer = tokenizers_module.Tokenizer

            return Tokenizer.from_file(path)
        except Exception:
            return None

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Conservative dependency-free token estimate for multilingual-e5-large.

        Models XLM-RoBERTa SentencePiece tokenization:
        - Base words split into subwords (~1.35x)
        - Symbols/punctuation each produce at least 1 token
        - Consecutive digits split into subwords (~0.5x per digit)
        - Character-density lower bound for dense text
        - Overhead tokens (<s>, </s>, passage, :)
        """
        words = len(text.split())
        chars = len(text)
        syms = len(re.findall(r"[^\w\s]", text))
        digits = len(re.findall(r"\d", text))
        token_est = 4 + int(words * 1.35 + syms * 1.1 + digits * 0.45 + 0.999)
        char_bound = int(chars / 3.2 + 0.999)
        word_bound = int(words * 1.6 + syms * 0.8 + 0.999)
        return max(token_est, char_bound, word_bound)

    def count_embedding_tokens(self, text: str) -> int:
        """Count tokens of the complete final embedding input (including passage: prefix)."""
        prefixed = f"{self.PASSAGE_PREFIX}{text}"
        if self._tokenizer is not None:
            return len(self._tokenizer.encode(prefixed).ids)
        return self.estimate_tokens(prefixed)

    def _format_heading_prefix(
        self, heading_path: tuple[str, ...] | list[str], policy_number: str | None = None
    ) -> str:
        """Deterministic heading formatter that preserves primary SOP identifier and parent/leaf.

        - If full heading fits budget (<= 75 tokens), returns full hierarchy.
        - If shortened, deterministically preserves:
            1. Root section / document title
            2. Primary SOP identifier (from policy_number or detected SOP pattern)
            3. Immediate parent section
            4. Immediate leaf section
        - Complete unshortened heading hierarchy is always recoverable via metadata.
        """
        if not heading_path:
            return policy_number or ""

        full_heading = " > ".join(heading_path)
        # Keep complete path if within reasonable budget (<= 75 tokens)
        if self.count_embedding_tokens(full_heading) <= 75:
            return full_heading

        if len(heading_path) <= 2:
            return full_heading

        # 1. Identify primary SOP identifier
        sop_seg_idx: int | None = None
        if policy_number:
            norm_pol = policy_number.strip().lower()
            for i, seg in enumerate(heading_path):
                if norm_pol in seg.lower():
                    sop_seg_idx = i
                    break
        if sop_seg_idx is None:
            for i, seg in enumerate(heading_path):
                has_sop_word = bool(re.search(r"(?i)\b(SOP|POL)\b", seg))
                has_sop_pfx = bool(re.search(r"(?i)\b(SOP|POL)[-\s#_]", seg))
                if has_sop_word or has_sop_pfx:
                    sop_seg_idx = i
                    break

        root = heading_path[0]
        parent = heading_path[-2]
        leaf = heading_path[-1]

        # 2. Build deterministic prefix preserving SOP identifier, parent, leaf
        prefix_parts: list[str] = []
        if policy_number and not (
            any(policy_number.lower() in s.lower() for s in (root, parent, leaf))
            or (
                sop_seg_idx is not None
                and policy_number.lower() in heading_path[sop_seg_idx].lower()
            )
        ):
            prefix_parts.append(f"[{policy_number}] {root}")
        else:
            prefix_parts.append(root)

        if sop_seg_idx is not None and sop_seg_idx not in (
            0,
            len(heading_path) - 2,
            len(heading_path) - 1,
        ):
            prefix_parts.append(heading_path[sop_seg_idx])

        prefix_parts.append("...")
        prefix_parts.append(parent)
        prefix_parts.append(leaf)

        shortened = " > ".join(prefix_parts)

        # 3. If individual headings are extremely verbose, bound segment lengths
        if self.count_embedding_tokens(shortened) > 75:
            bounded_parts: list[str] = []
            for p in prefix_parts:
                if p == "...":
                    bounded_parts.append(p)
                else:
                    words = p.split()
                    if len(words) > 10:
                        bounded_parts.append(" ".join(words[:10]) + "...")
                    else:
                        bounded_parts.append(p)
            shortened = " > ".join(bounded_parts)

        return shortened

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
            step = min(self.MAX_WORDS, 50)
            for i in range(0, len(words), step):
                seg = " ".join(words[i : i + step])
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

        def part_fits(col_dict: dict[int, str]) -> bool:
            line = row_line_for(col_dict)
            full_text = f"{heading}\n" + "\n".join([*header_lines, line])
            tokens = self.count_embedding_tokens(full_text)
            words = len(line.split())
            return tokens <= self.SOFT_TARGET_TOKENS and words <= self.MAX_WORDS

        current_cols: dict[int, str] = {}

        for c in range(1, num_cols):
            cell_text = row_cells[c]
            if not cell_text:
                continue

            cell_words = len(cell_text.split())
            test_row_single = row_line_for({c: cell_text})
            test_tokens_single = self.count_embedding_tokens(
                f"{heading}\n" + "\n".join([*header_lines, test_row_single])
            )

            if cell_words > self.MAX_WORDS or test_tokens_single > self.SOFT_TARGET_TOKENS:
                if current_cols:
                    parts.append([*header_lines, row_line_for(current_cols)])
                    current_cols = {}

                words = cell_text.split()
                step = min(self.MAX_WORDS, 50)
                seg_words: list[str] = []
                for w in words:
                    test_seg = seg_words + [w]
                    test_line = row_line_for({c: " ".join(test_seg)})
                    test_toks = self.count_embedding_tokens(
                        f"{heading}\n" + "\n".join([*header_lines, test_line])
                    )
                    if seg_words and (
                        len(test_seg) > step or test_toks > self.SOFT_TARGET_TOKENS
                    ):
                        parts.append([*header_lines, row_line_for({c: " ".join(seg_words)})])
                        seg_words = [w]
                    else:
                        seg_words.append(w)
                if seg_words:
                    parts.append([*header_lines, row_line_for({c: " ".join(seg_words)})])
            else:
                test_cols = dict(current_cols)
                test_cols[c] = cell_text
                test_line = row_line_for(test_cols)
                test_toks = self.count_embedding_tokens(
                    f"{heading}\n" + "\n".join([*header_lines, test_line])
                )
                if (
                    row_words(test_cols) <= self.MAX_WORDS
                    and test_toks <= self.SOFT_TARGET_TOKENS
                ) or not current_cols:
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
    ) -> list[RetrievalChunk]:
        chunks: list[RetrievalChunk] = []
        current_text: list[str] = []
        chunk_index = 0

        heading_prefix = self._format_heading_prefix(
            section.heading_path, section.policy_number
        )

        def can_fit_lines(extra_lines: list[str]) -> bool:
            candidate_text = f"{heading_prefix}\n" + "\n".join(current_text + extra_lines)
            tokens = self.count_embedding_tokens(candidate_text)
            body_words = sum(len(line.split()) for line in current_text + extra_lines)
            return tokens <= self.SOFT_TARGET_TOKENS and body_words <= self.MAX_WORDS

        def flush() -> None:
            nonlocal current_text, chunk_index
            if not current_text:
                return

            text = f"{heading_prefix}\n" + "\n".join(current_text)
            final_tokens = self.count_embedding_tokens(text)
            if final_tokens > self.HARD_MAX_TOKENS:
                raise ValueError(
                    f"Chunk {document.version_id}:{section.id}:{chunk_index} exceeds hard maximum "
                    f"of {self.HARD_MAX_TOKENS} tokens (observed {final_tokens} tokens). "
                    f"Document {document.id}, section {section.id}."
                )

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
                    if can_fit_lines(header_lines):
                        current_text.extend(header_lines)
                    else:
                        flush()
                        current_text.extend(header_lines)
                    continue

                temp_table_lines = list(header_lines)
                table_body_words = 0

                for row_cells in data_rows:
                    line = "| " + " | ".join(row_cells) + " |"
                    line_words = len(line.split())
                    row_test_text = f"{heading_prefix}\n" + "\n".join(header_lines + [line])
                    row_tokens = self.count_embedding_tokens(row_test_text)

                    if line_words > self.MAX_WORDS or row_tokens > self.SOFT_TARGET_TOKENS:
                        if len(temp_table_lines) > len(header_lines):
                            current_text.extend(temp_table_lines)
                        if current_text:
                            flush()
                        temp_table_lines = list(header_lines)
                        table_body_words = 0

                        part_lines_list = self._split_oversized_table_row(
                            grid_headers,
                            row_cells,
                            caption=caption,
                            heading=heading_prefix,
                        )
                        for part_lines in part_lines_list:
                            current_text = list(part_lines)
                            flush()

                        temp_table_lines = list(header_lines)
                        table_body_words = 0
                        continue

                    # Check budget
                    cand_text = f"{heading_prefix}\n" + "\n".join(
                        current_text + temp_table_lines + [line]
                    )
                    cand_tokens = self.count_embedding_tokens(cand_text)
                    curr_body_words = sum(len(line_item.split()) for line_item in current_text)

                    if (
                        curr_body_words + table_body_words + line_words > self.MAX_WORDS
                        or cand_tokens > self.SOFT_TARGET_TOKENS
                    ) and (current_text or len(temp_table_lines) > len(header_lines)):
                        if len(temp_table_lines) > len(header_lines):
                            current_text.extend(temp_table_lines)
                        flush()
                        temp_table_lines = list(header_lines)
                        table_body_words = 0

                    temp_table_lines.append(line)
                    table_body_words += line_words

                if len(temp_table_lines) > len(header_lines):
                    current_text.extend(temp_table_lines)

                continue

            block_text = self._serialize_block(block)
            lines = [line for line in block_text.split("\n") if line.strip()] or [block_text]

            for line in lines:
                line_words = len(line.split())
                line_test = f"{heading_prefix}\n" + line
                line_tokens = self.count_embedding_tokens(line_test)

                if line_words > self.MAX_WORDS or line_tokens > self.SOFT_TARGET_TOKENS:
                    if current_text:
                        flush()
                    words = line.split()
                    seg: list[str] = []
                    for w in words:
                        test_seg = seg + [w]
                        test_cand = f"{heading_prefix}\n" + " ".join(test_seg)
                        if seg and (
                            len(test_seg) > self.MAX_WORDS
                            or self.count_embedding_tokens(test_cand) > self.SOFT_TARGET_TOKENS
                        ):
                            current_text.append(" ".join(seg))
                            flush()
                            seg = [w]
                        else:
                            seg.append(w)
                    if seg:
                        current_text.append(" ".join(seg))
                        flush()
                    continue

                if not can_fit_lines([line]) and current_text:
                    flush()

                current_text.append(line)

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
