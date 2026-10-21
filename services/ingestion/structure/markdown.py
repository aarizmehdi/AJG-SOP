from packages.contracts.canonical import BlockKind, CanonicalBlock, CanonicalListItem, CanonicalSOP


def _list_lines(item: CanonicalListItem, ordered: bool, index: int, depth: int) -> list[str]:
    marker = item.marker or (f"{index}." if ordered else "-")
    lines = [f"{'  ' * depth}{marker} {item.text}"]
    for child_index, child in enumerate(item.children, start=1):
        lines.extend(
            _list_lines(
                child, bool(child.marker and child.marker[0].isdigit()), child_index, depth + 1
            )
        )
    return lines


def canonical_to_markdown(document: CanonicalSOP) -> str:
    lines = [f"# {document.title}", ""]
    for section in document.sections:
        # Canonical levels already express the source hierarchy. Adding another
        # level on every export progressively demotes policies on re-ingestion.
        if section.heading_level != 1 or section.heading != document.title:
            prefix = "#" * min(6, max(2, section.heading_level))
            lines.extend([f"{prefix} {section.heading}", ""])
        lines.extend([blocks_to_markdown(section.blocks), ""])
    return "\n".join(lines).strip() + "\n"


def blocks_to_markdown(blocks: list[CanonicalBlock]) -> str:
    """Readable source structure shared by export, reading and version comparison."""
    lines: list[str] = []
    for block in blocks:
        if block.kind is BlockKind.PARAGRAPH and block.text:
            lines.extend([block.text, ""])
        elif block.kind in {BlockKind.ORDERED_LIST, BlockKind.UNORDERED_LIST}:
            for index, item in enumerate(block.list_items, start=1):
                lines.extend(_list_lines(item, block.kind is BlockKind.ORDERED_LIST, index, 0))
            lines.append("")
        elif block.kind is BlockKind.TABLE and block.table:
            rows: dict[int, dict[int, str]] = {}
            for cell in block.table.cells:
                rows.setdefault(cell.row, {})[cell.column] = cell.text
            columns = max((cell.column for cell in block.table.cells), default=-1) + 1
            ordered_rows = sorted(rows)
            if ordered_rows and columns:
                for index, row in enumerate(ordered_rows):
                    lines.append(
                        "| "
                        + " | ".join(
                            _escape_table_cell(rows[row].get(column, ""))
                            for column in range(columns)
                        )
                        + " |"
                    )
                    if index == 0:
                        lines.append("| " + " | ".join("---" for _ in range(columns)) + " |")
            lines.append("")
    return "\n".join(lines).strip()


def _escape_table_cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", " ")
