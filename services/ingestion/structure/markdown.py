from packages.contracts.canonical import BlockKind, CanonicalSOP


def canonical_to_markdown(document: CanonicalSOP) -> str:
    lines = [f"# {document.title}", ""]
    for section in document.sections:
        prefix = "#" * min(6, section.heading_level + 1)
        lines.extend([f"{prefix} {section.heading}", ""])
        for block in section.blocks:
            if block.kind is BlockKind.PARAGRAPH and block.text:
                lines.extend([block.text, ""])
            elif block.kind in {BlockKind.ORDERED_LIST, BlockKind.UNORDERED_LIST}:
                for index, item in enumerate(block.list_items, start=1):
                    marker = f"{index}." if block.kind is BlockKind.ORDERED_LIST else "-"
                    lines.append(f"{'  ' * item.level}{marker} {item.text}")
                lines.append("")
            elif block.kind is BlockKind.TABLE and block.table:
                rows: dict[int, dict[int, str]] = {}
                for cell in block.table.cells:
                    rows.setdefault(cell.row, {})[cell.column] = cell.text
                columns = max(
                    (cell.column for cell in block.table.cells), default=-1
                ) + 1
                ordered_rows = sorted(rows)
                if ordered_rows and columns:
                    header_row = ordered_rows[0]
                    lines.append(
                        "| "
                        + " | ".join(
                            _escape_table_cell(rows[header_row].get(column, ""))
                            for column in range(columns)
                        )
                        + " |"
                    )
                    lines.append("| " + " | ".join("---" for _ in range(columns)) + " |")
                    for row in ordered_rows[1:]:
                        lines.append(
                            "| "
                            + " | ".join(
                                _escape_table_cell(rows[row].get(column, ""))
                                for column in range(columns)
                            )
                            + " |"
                        )
                lines.append("")
    return "\n".join(lines).strip() + "\n"


def _escape_table_cell(value: str) -> str:
    return value.replace("|", r"\|").replace("\n", " ")
